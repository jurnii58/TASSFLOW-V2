#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use tauri::{
    AppHandle, CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem, WindowEvent,
};

fn create_system_tray() -> SystemTray {
    let open_item = CustomMenuItem::new("open".to_string(), "🟢 Abrir TASSFLOW");
    let admin_item = CustomMenuItem::new("admin".to_string(), "📊 Panel Administrativo");
    let status_item = CustomMenuItem::new("status".to_string(), "⚡ Transmitiendo a Mosquitto (1 Hz, QoS 0)").disabled();
    let quit_item = CustomMenuItem::new("quit".to_string(), "🛑 Salir por completo");

    let tray_menu = SystemTrayMenu::new()
        .add_item(open_item)
        .add_item(admin_item)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(status_item)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit_item);

    SystemTray::new().with_menu(tray_menu)
}

fn handle_tray_event(app: &AppHandle, event: SystemTrayEvent) {
    match event {
        SystemTrayEvent::LeftClick { .. } | SystemTrayEvent::DoubleClick { .. } => {
            if let Some(window) = app.get_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }
        SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
            "open" => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "admin" => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.eval("window.location.href = '/admin'");
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                std::process::exit(0);
            }
            _ => {}
        },
        _ => {}
    }
}

fn main() {
    tauri::Builder::default()
        .system_tray(create_system_tray())
        .on_system_tray_event(handle_tray_event)
        .on_window_event(|event| {
            if let WindowEvent::CloseRequested { api, .. } = event.event() {
                // Al presionar 'X', ocultar en segundo plano dentro de la bandeja del sistema
                let _ = event.window().hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

