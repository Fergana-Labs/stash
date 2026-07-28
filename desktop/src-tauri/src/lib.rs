mod api;
mod checks;
mod config;
mod curator;
mod install;
mod signin;
mod uploads;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            checks::run_checks,
            api::backend_health,
            api::whoami,
            api::list_integrations,
            api::list_sources,
            api::curator_status,
            api::recompute_memory,
            signin::signin_start,
            signin::signin_poll,
            install::install_cli,
            install::install_plugin,
            uploads::upload_settings,
            uploads::set_streaming,
            uploads::exclude_path,
            uploads::include_path,
            curator::curator_local_status,
            curator::curator_run_now,
            curator::curator_set_enabled,
            curator::curator_set_interval,
        ])
        .setup(|app| {
            extend_path_for_gui_launch();
            curator::ensure_state_files()?;
            curator::start_scheduler();
            build_tray(app)?;
            Ok(())
        })
        // Closing the window hides it; the scheduler keeps running in the tray.
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Stash Desktop", true, None::<&str>)?;
    let run = MenuItem::with_id(app, "run_curator", "Run curator now", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &run, &quit])?;
    TrayIconBuilder::new()
        .icon(
            app.default_window_icon()
                .expect("no default window icon")
                .clone(),
        )
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            }
            // spawn_run fetches the prompt over HTTP; keep that off the
            // event thread.
            "run_curator" => {
                std::thread::spawn(|| {
                    if let Err(e) = curator::spawn_run() {
                        eprintln!("tray run curator: {e}");
                    }
                });
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .build(app)?;
    Ok(())
}

/// Finder-launched apps get a minimal PATH (/usr/bin:/bin:…), which hides the
/// `stash` and `claude` CLIs. Append the places they actually live.
fn extend_path_for_gui_launch() {
    let home = dirs::home_dir().expect("no home directory");
    let extras = [
        home.join(".local/bin"),
        "/opt/homebrew/bin".into(),
        "/usr/local/bin".into(),
    ];
    let current = std::env::var("PATH").unwrap_or_default();
    let mut parts: Vec<String> = std::env::split_paths(&current)
        .map(|p| p.to_string_lossy().into_owned())
        .collect();
    for extra in extras {
        let s = extra.to_string_lossy().into_owned();
        if !parts.contains(&s) {
            parts.push(s);
        }
    }
    std::env::set_var("PATH", parts.join(":"));
}
