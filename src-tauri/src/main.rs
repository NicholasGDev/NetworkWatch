#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Inicializa a janela Tauri, o backend local e o ícone da bandeja do NetWatch.

use std::{
    io::{BufRead, BufReader},
    process::{Child, Command, Stdio},
    sync::{mpsc, Mutex},
    time::Duration,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};
#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Mantém o processo filho do backend e encerra-o ao descartar o estado.
struct Backend(Mutex<Option<Child>>);
impl Drop for Backend {
    /// Finaliza e aguarda o backend para evitar processos órfãos.
    fn drop(&mut self) {
        if let Ok(child) = self.0.get_mut() {
            if let Some(mut child) = child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

/// Exibe e focaliza a janela principal se ela estiver disponível.
fn show_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Configura o ciclo de vida da janela, do backend e do ícone da bandeja.
fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        // Minimizar esconde a janela; ela volta pelo ícone na área de ícones ocultos.
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Resized(_) = event {
                if window.is_minimized().unwrap_or(false) {
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            let mut cmd;
            if cfg!(debug_assertions) {
                let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
                let python = std::env::var_os("SCROLLANSWER_PYTHON")
                    .map(std::path::PathBuf::from)
                    .unwrap_or_else(|| root.join(".venv/Scripts/python.exe"));
                cmd = Command::new(python);
                cmd.arg(root.join("backend.py")).current_dir(root);
            } else {
                cmd = Command::new(app.path().resource_dir()?.join("backend/netwatch-service.exe"));
            }
            #[cfg(windows)]
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW: no console flash.
            cmd.stdout(Stdio::piped()).stderr(Stdio::null());
            let mut child = cmd.spawn()?;
            let stdout = child.stdout.take().unwrap();
            let guard = Backend(Mutex::new(Some(child)));
            let (tx, rx) = mpsc::channel();
            std::thread::spawn(move || {
                let mut line = String::new();
                let result = BufReader::new(stdout).read_line(&mut line).map(|_| line);
                let _ = tx.send(result);
            });
            let line = rx.recv_timeout(Duration::from_secs(30))??;
            let ready: serde_json::Value = serde_json::from_str(&line)?;
            let address = ready["url"].as_str().ok_or("Backend did not provide a URL")?;
            let url: tauri::Url = address.parse()?;
            if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") {
                return Err("Invalid backend address".into());
            }
            let allowed_port = url.port();
            app.manage(guard);
            tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::External(url))
                .title("NetWatch — Monitor de Rede")
                .skip_taskbar(true)
                .inner_size(840.0, 760.0)
                .min_inner_size(540.0, 460.0)
                .on_navigation(move |url| url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.port() == allowed_port)
                .build()?;
            let open = MenuItem::with_id(app, "open", "Abrir", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
            // Sem tooltip: o ícone não exibe o nome do app.
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().cloned().ok_or("Icon missing")?)
                .menu(&Menu::with_items(app, &[&open, &quit])?)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        show_main(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Falha ao iniciar NetWatch. Verifique Python, dependências e config.json.");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(backend) = handle.try_state::<Backend>() {
                if let Ok(mut guard) = backend.0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        }
    });
}
