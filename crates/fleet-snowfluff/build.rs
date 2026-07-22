fn main() {
    // Generates `build::SHORT_COMMIT` (among other build-time constants),
    // used by commands::build_commit for the about tab's "Build: {hash}"
    // line -- degrades gracefully on its own for a build from a source
    // tarball with no `.git` available.
    shadow_rs::ShadowBuilder::builder().build().unwrap();

    tauri_build::build()
}
