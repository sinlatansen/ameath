//! Shared wgpu context (one instance/adapter/device/queue/pipeline for
//! the whole app, task 6.2) and the per-window transparent surface each
//! pet renders into. Generalizes the pipeline proven in
//! `examples/transparent_gif.rs` (see design.md D14) to arbitrary
//! window sizes and many windows sharing one GPU device.

use crate::animation::AnimationFrame;

pub struct GpuContext {
    pub device: wgpu::Device,
    pub queue: wgpu::Queue,
    pub adapter: wgpu::Adapter,
    pub pipeline: wgpu::RenderPipeline,
    pub bind_group_layout: wgpu::BindGroupLayout,
    pub sampler: wgpu::Sampler,
    pub format: wgpu::TextureFormat,
    pub alpha_mode: wgpu::CompositeAlphaMode,
}

/// Picks the best available alpha-compositing mode for a genuinely
/// transparent surface; see design.md D14 for the per-platform notes.
fn pick_alpha_mode(caps: &wgpu::SurfaceCapabilities) -> wgpu::CompositeAlphaMode {
    for preferred in
        [wgpu::CompositeAlphaMode::PostMultiplied, wgpu::CompositeAlphaMode::PreMultiplied]
    {
        if caps.alpha_modes.contains(&preferred) {
            return preferred;
        }
    }
    log::warn!(
        "surface does not advertise a transparent alpha mode (got {:?}); pet windows will NOT be \
         see-through",
        caps.alpha_modes
    );
    wgpu::CompositeAlphaMode::Opaque
}

impl GpuContext {
    /// Bootstraps the shared GPU context using `bootstrap_surface` (the
    /// first pet window created) purely to pick a compatible adapter;
    /// every subsequent window creates its own surface against the same
    /// device (see `PetSurface::new`).
    pub fn new(instance: &wgpu::Instance, bootstrap_surface: &wgpu::Surface) -> Self {
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::LowPower,
            compatible_surface: Some(bootstrap_surface),
            force_fallback_adapter: false,
        }))
        .expect("request wgpu adapter");

        let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
            label: Some("fleet-snowfluff-device"),
            required_features: wgpu::Features::empty(),
            required_limits: wgpu::Limits::downlevel_webgl2_defaults(),
            memory_hints: Default::default(),
            trace: wgpu::Trace::Off,
            experimental_features: wgpu::ExperimentalFeatures::disabled(),
        }))
        .expect("request wgpu device");

        let caps = bootstrap_surface.get_capabilities(&adapter);
        let format = caps.formats.iter().copied().find(|f| f.is_srgb()).unwrap_or(caps.formats[0]);
        let alpha_mode = pick_alpha_mode(&caps);
        log::info!("wgpu alpha modes available: {:?}; chose {:?}", caps.alpha_modes, alpha_mode);

        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pet-quad-shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("pet_quad.wgsl").into()),
        });

        let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pet-bind-group-layout"),
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
                wgpu::BindGroupLayoutEntry {
                    binding: 2,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Buffer {
                        ty: wgpu::BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                },
            ],
        });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pet-pipeline-layout"),
            bind_group_layouts: &[&bind_group_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("pet-quad-pipeline"),
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

        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("pet-sampler"),
            mag_filter: wgpu::FilterMode::Nearest,
            min_filter: wgpu::FilterMode::Nearest,
            ..Default::default()
        });

        Self { device, queue, adapter, pipeline, bind_group_layout, sampler, format, alpha_mode }
    }
}

/// The transparent surface a single pet window renders into.
pub struct PetSurface {
    surface: wgpu::Surface<'static>,
    config: wgpu::SurfaceConfiguration,
    opacity_buffer: wgpu::Buffer,
}

impl PetSurface {
    pub fn new(gpu: &GpuContext, surface: wgpu::Surface<'static>, width: u32, height: u32) -> Self {
        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format: gpu.format,
            width: width.max(1),
            height: height.max(1),
            present_mode: wgpu::PresentMode::Fifo,
            alpha_mode: gpu.alpha_mode,
            view_formats: vec![],
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&gpu.device, &config);

        // 16 bytes: a single f32 padded to the platform's minimum uniform
        // buffer binding alignment.
        let opacity_buffer = gpu.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pet-opacity-uniform"),
            size: 16,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let mut initial = [0u8; 16];
        initial[0..4].copy_from_slice(&1.0f32.to_le_bytes());
        gpu.queue.write_buffer(&opacity_buffer, 0, &initial);

        Self { surface, config, opacity_buffer }
    }

    pub fn resize(&mut self, gpu: &GpuContext, width: u32, height: u32) {
        self.config.width = width.max(1);
        self.config.height = height.max(1);
        self.surface.configure(&gpu.device, &self.config);
    }

    pub fn set_opacity(&self, gpu: &GpuContext, opacity: f32) {
        let mut bytes = [0u8; 16];
        bytes[0..4].copy_from_slice(&opacity.clamp(0.0, 1.0).to_le_bytes());
        gpu.queue.write_buffer(&self.opacity_buffer, 0, &bytes);
    }

    /// Uploads `frame` (must be `frame_w x frame_h` RGBA8) and draws it,
    /// stretched to fill the whole surface -- scale (task 6.5) is
    /// achieved by the surface/window already being sized to
    /// `native_size * scale`, so no per-vertex scale math is needed here.
    pub fn render(&self, gpu: &GpuContext, frame: &AnimationFrame, frame_w: u32, frame_h: u32) {
        let texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("pet-frame-texture"),
            size: wgpu::Extent3d { width: frame_w, height: frame_h, depth_or_array_layers: 1 },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8UnormSrgb,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        gpu.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            &frame.rgba,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(4 * frame_w),
                rows_per_image: Some(frame_h),
            },
            wgpu::Extent3d { width: frame_w, height: frame_h, depth_or_array_layers: 1 },
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let bind_group = gpu.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pet-frame-bind-group"),
            layout: &gpu.bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&gpu.sampler),
                },
                wgpu::BindGroupEntry {
                    binding: 2,
                    resource: self.opacity_buffer.as_entire_binding(),
                },
            ],
        });

        let output = match self.surface.get_current_texture() {
            Ok(frame) => frame,
            Err(wgpu::SurfaceError::Lost | wgpu::SurfaceError::Outdated) => {
                self.surface.configure(&gpu.device, &self.config);
                return;
            }
            Err(e) => {
                log::error!("surface error: {e:?}");
                return;
            }
        };
        let output_view = output.texture.create_view(&wgpu::TextureViewDescriptor::default());

        let mut encoder = gpu.device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("pet-frame-encoder"),
        });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("pet-frame-pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &output_view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            pass.set_pipeline(&gpu.pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.draw(0..6, 0..1);
        }
        gpu.queue.submit(std::iter::once(encoder.finish()));
        output.present();
    }
}
