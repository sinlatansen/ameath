//! Spike (tasks 3.1-3.5): a plain, non-webview, transparent, borderless
//! window that decodes a GIF and blits its frames via wgpu with real
//! per-pixel alpha (no chroma-key). Verified visually on macOS (Metal):
//! the sprite composites directly over arbitrary desktop content with no
//! backing box of any color. See design.md's "Windows spike findings"
//! notes for the full writeup, including two real gotchas found here:
//!
//! - macOS transparency needs the `tauri` crate's `macos-private-api` Cargo
//!   feature AND `app.macOSPrivateApi: true` in tauri.conf.json, or
//!   `.transparent()` doesn't even compile.
//! - A genuinely windowless window needs the `unstable` Cargo feature
//!   (`tauri::window::WindowBuilder`, not `WebviewWindowBuilder`).
//!
//! The Windows alpha-compositing path is written against wgpu/Tauri's
//! documented transparent-surface behavior but is UNVERIFIED — this
//! machine has no Windows hardware to run it on. See the "Windows note"
//! comments below and design.md's Risks section.
//!
//! Run with: cargo run --example transparent_gif -p fleet-snowfluff

use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

use image::AnimationDecoder;
use tauri::Manager;

struct GifFrame {
    rgba: Vec<u8>,
    delay: Duration,
}

struct Renderer {
    surface: wgpu::Surface<'static>,
    device: wgpu::Device,
    queue: wgpu::Queue,
    pipeline: wgpu::RenderPipeline,
    bind_group_layout: wgpu::BindGroupLayout,
    sampler: wgpu::Sampler,
    config: wgpu::SurfaceConfiguration,
    frames: Vec<GifFrame>,
    frame_index: usize,
    frame_started_at: Instant,
    width: u32,
    height: u32,
}

fn decode_gif(bytes: &[u8]) -> (Vec<GifFrame>, u32, u32) {
    let decoder =
        image::codecs::gif::GifDecoder::new(std::io::Cursor::new(bytes)).expect("valid gif");
    let mut width = 0u32;
    let mut height = 0u32;
    let frames = decoder
        .into_frames()
        .collect_frames()
        .expect("decode gif frames")
        .into_iter()
        .map(|frame| {
            let delay: Duration = frame.delay().into();
            let buf = frame.into_buffer();
            width = buf.width();
            height = buf.height();
            GifFrame {
                rgba: buf.into_raw(),
                // Some GIFs encode a zero delay; floor it so we don't spin.
                delay: if delay.is_zero() { Duration::from_millis(80) } else { delay },
            }
        })
        .collect();
    (frames, width, height)
}

fn make_pipeline(
    device: &wgpu::Device,
    format: wgpu::TextureFormat,
) -> (wgpu::RenderPipeline, wgpu::BindGroupLayout) {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gif-quad-shader"),
        source: wgpu::ShaderSource::Wgsl(include_str!("transparent_gif.wgsl").into()),
    });

    let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: Some("gif-bind-group-layout"),
        entries: &[
            wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                    view_dimension: wgpu::TextureViewDimension::D2,
                    multisampled: false,
                },
                count: None,
            },
            wgpu::BindGroupLayoutEntry {
                binding: 1,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                count: None,
            },
        ],
    });

    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gif-pipeline-layout"),
        bind_group_layouts: &[&bind_group_layout],
        push_constant_ranges: &[],
    });

    // Straight (non-premultiplied) alpha blend: our decoded RGBA frames are
    // straight alpha, matching the GIF's own transparency semantics.
    let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("gif-quad-pipeline"),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            buffers: &[],
            compilation_options: Default::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some("fs_main"),
            targets: &[Some(wgpu::ColorTargetState {
                format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
            compilation_options: Default::default(),
        }),
        primitive: wgpu::PrimitiveState::default(),
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    });

    (pipeline, bind_group_layout)
}

/// Picks the best available alpha-compositing mode for a genuinely
/// transparent (not just blended-to-black) window surface.
///
/// - macOS (Metal): `PostMultiplied` is commonly advertised and is what we
///   verified visually on this machine.
/// - Windows (DX12/DX11 via wgpu -> DirectComposition when the Tauri window is
///   created with `.transparent(true)`): wgpu is expected to advertise
///   `PostMultiplied` or `PreMultiplied` when DirectComposition backs the
///   swapchain. UNVERIFIED on real hardware. If neither is offered, that is the
///   documented signal (task 3.5) to fall back to a manual
///   `UpdateLayeredWindow` blit path instead of a wgpu swapchain.
/// - Linux/X11 with a compositor: `PostMultiplied`/`PreMultiplied` are
///   typically available; without a compositor there is no real per-pixel alpha
///   and we fall back to `Opaque`.
fn pick_alpha_mode(caps: &wgpu::SurfaceCapabilities) -> wgpu::CompositeAlphaMode {
    for preferred in
        [wgpu::CompositeAlphaMode::PostMultiplied, wgpu::CompositeAlphaMode::PreMultiplied]
    {
        if caps.alpha_modes.contains(&preferred) {
            return preferred;
        }
    }
    log::warn!(
        "surface does not advertise a transparent alpha mode (got {:?}); falling back to Opaque \
         -- window will NOT be see-through",
        caps.alpha_modes
    );
    wgpu::CompositeAlphaMode::Opaque
}

fn create_renderer(window: tauri::window::Window, gif_bytes: &[u8]) -> Renderer {
    let (frames, width, height) = decode_gif(gif_bytes);

    let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor::default());
    let surface = instance.create_surface(window).expect("create wgpu surface from window");

    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::LowPower,
        compatible_surface: Some(&surface),
        force_fallback_adapter: false,
    }))
    .expect("request wgpu adapter");

    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        label: Some("gif-spike-device"),
        required_features: wgpu::Features::empty(),
        required_limits: wgpu::Limits::downlevel_webgl2_defaults(),
        memory_hints: Default::default(),
        trace: wgpu::Trace::Off,
        experimental_features: wgpu::ExperimentalFeatures::disabled(),
    }))
    .expect("request wgpu device");

    let caps = surface.get_capabilities(&adapter);
    let format = caps.formats.iter().copied().find(|f| f.is_srgb()).unwrap_or(caps.formats[0]);
    let alpha_mode = pick_alpha_mode(&caps);
    log::info!("surface alpha modes available: {:?}; chose {:?}", caps.alpha_modes, alpha_mode);

    let config = wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format,
        width: width.max(1),
        height: height.max(1),
        present_mode: wgpu::PresentMode::Fifo,
        alpha_mode,
        view_formats: vec![],
        desired_maximum_frame_latency: 2,
    };
    surface.configure(&device, &config);

    let (pipeline, bind_group_layout) = make_pipeline(&device, format);
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        label: Some("gif-sampler"),
        mag_filter: wgpu::FilterMode::Nearest,
        min_filter: wgpu::FilterMode::Nearest,
        ..Default::default()
    });

    Renderer {
        surface,
        device,
        queue,
        pipeline,
        bind_group_layout,
        sampler,
        config,
        frames,
        frame_index: 0,
        frame_started_at: Instant::now(),
        width,
        height,
    }
}

impl Renderer {
    fn upload_frame_texture(&self, frame: &GifFrame) -> wgpu::BindGroup {
        let texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("gif-frame-texture"),
            size: wgpu::Extent3d {
                width: self.width,
                height: self.height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8UnormSrgb,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        self.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            &frame.rgba,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(4 * self.width),
                rows_per_image: Some(self.height),
            },
            wgpu::Extent3d { width: self.width, height: self.height, depth_or_array_layers: 1 },
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gif-frame-bind-group"),
            layout: &self.bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&self.sampler),
                },
            ],
        })
    }

    /// Advances to the next GIF frame if its delay has elapsed, then draws
    /// the current frame. Returns `false` once we've looped enough times to
    /// call the spike complete.
    fn render(&mut self, loops_remaining: &mut u32) -> bool {
        if self.frames.is_empty() {
            return false;
        }
        let current_delay = self.frames[self.frame_index].delay;
        if self.frame_started_at.elapsed() >= current_delay {
            self.frame_index += 1;
            if self.frame_index >= self.frames.len() {
                self.frame_index = 0;
                *loops_remaining = loops_remaining.saturating_sub(1);
            }
            self.frame_started_at = Instant::now();
        }

        let bind_group = self.upload_frame_texture(&self.frames[self.frame_index]);

        let output = match self.surface.get_current_texture() {
            Ok(frame) => frame,
            Err(wgpu::SurfaceError::Lost | wgpu::SurfaceError::Outdated) => {
                self.surface.configure(&self.device, &self.config);
                return *loops_remaining > 0;
            }
            Err(e) => {
                log::error!("surface error: {e:?}");
                return *loops_remaining > 0;
            }
        };
        let view = output.texture.create_view(&wgpu::TextureViewDescriptor::default());

        let mut encoder = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("gif-frame-encoder"),
        });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("gif-frame-pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        // Fully transparent clear -- this is the whole point
                        // of the spike: no chroma-key backing color.
                        load: wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            pass.set_pipeline(&self.pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.draw(0..6, 0..1);
        }
        self.queue.submit(std::iter::once(encoder.finish()));
        output.present();

        *loops_remaining > 0
    }
}

fn main() {
    env_logger::init();

    let gif_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| format!("{}/../../assets/gifs/idle1.gif", env!("CARGO_MANIFEST_DIR")));
    let gif_bytes =
        std::fs::read(&gif_path).unwrap_or_else(|e| panic!("failed to read {gif_path}: {e}"));

    tauri::Builder::default()
        .setup(move |app| {
            // Genuinely windowless per D2 -- no webview at all, just an OS
            // window handle for wgpu to target directly. `tauri.conf.json`
            // declares zero default windows (matches D8's "settings window
            // doesn't auto-open" requirement) -- confirmed that alone does
            // NOT stop this window from appearing; Regular is also already
            // Tauri's documented default, kept explicit here for clarity.
            #[cfg(target_os = "macos")]
            app.handle().set_activation_policy(tauri::ActivationPolicy::Regular)?;

            let window = tauri::window::WindowBuilder::new(app, "gif-spike")
                .title("Fleet Snowfluff -- transparency spike")
                .decorations(false)
                .transparent(true)
                .always_on_top(true)
                .resizable(false)
                .skip_taskbar(true)
                .inner_size(200.0, 200.0)
                // NOTE: .center() produced an invisible/off-screen window
                // in this environment (root cause unconfirmed -- possibly
                // monitor geometry not yet resolved for a windowless
                // window at build time). An explicit .position() is the
                // verified-working alternative; worth re-testing .center()
                // once this becomes the production pet-window path (task
                // 6.1), since pets do need reliable placement logic.
                .position(400.0, 400.0)
                .build()?;
            window.set_focus()?;

            let renderer = create_renderer(window, &gif_bytes);
            app.manage(Mutex::new(renderer));
            app.manage(Mutex::new(3u32)); // loop the gif 3x then exit

            // Tauri's event loop defaults to ControlFlow::Wait and blocks
            // between real OS events, so MainEventsCleared alone won't
            // drive a continuous animation. Instead, a ticking background
            // thread schedules each frame's render onto the main thread via
            // run_on_main_thread, which is the pattern the production pet
            // tick (D2/D4, ~30ms) will use too.
            let app_handle = app.handle().clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_millis(16));
                let handle = app_handle.clone();
                let result = app_handle.run_on_main_thread(move || {
                    let renderer_state = handle.state::<Mutex<Renderer>>();
                    let loops_state = handle.state::<Mutex<u32>>();
                    let mut renderer = renderer_state.lock().unwrap();
                    let mut loops_remaining = loops_state.lock().unwrap();
                    let keep_going = renderer.render(&mut loops_remaining);
                    if !keep_going {
                        handle.exit(0);
                    }
                });
                if result.is_err() {
                    break;
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri app")
        .run(|_app_handle, _event| {});
}
