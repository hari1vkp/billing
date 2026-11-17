use std::process::Command;

/// `print_file` — hand a generated file to the OS print subsystem.
#[tauri::command]
pub fn print_file(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        // Single-quote escaping for PowerShell string literals.
        let script = format!(
            "Start-Process -Verb Print -FilePath '{}'",
            path.replace('\'', "''")
        );
        let status = Command::new("powershell")
            .args(["-NoProfile", "-Command", &script])
            .status()
            .map_err(|e| format!("Could not start PowerShell: {e}"))?;
        if status.success() {
            Ok(())
        } else {
            Err(format!("Print command failed with status {status}"))
        }
    }

    #[cfg(target_os = "linux")]
    {
        let status = match Command::new("xdg-open").arg(&path).status() {
            Ok(status) if status.success() => return Ok(()),
            _ => Command::new("gio").args(["open", &path]).status(),
        };
        match status {
            Ok(status) if status.success() => Ok(()),
            Ok(status) => Err(format!("Print command failed with status {status}")),
            Err(e) => Err(format!("Could not open file for printing: {e}")),
        }
    }

    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        let _ = path;
        Err("Printing is not supported on this platform".into())
    }
}
