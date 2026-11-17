import { invoke } from '@tauri-apps/api/core';

/** Shape returned by the `app_info` Tauri command. */
export interface AppInfo {
  version: string;
  data_dir: string;
  db_path: string;
  platform: string;
}

/** Shape returned by the `local_db_status` Tauri command. */
export interface LocalDbStatus {
  exists: boolean;
  path: string;
  tables: number;
}

/** True when running inside the Tauri desktop shell. */
export function isTauri(): boolean {
  return '__TAURI_INTERNALS__' in window;
}

/** Typed wrapper for the `app_info` command. */
export function appInfo(): Promise<AppInfo> {
  return invoke<AppInfo>('app_info');
}

let cachedBackendUrl: string | null = null;

/**
 * Resolve the configured backend API base URL. The value is cached after the
 * first successful call so the API client only has to resolve it once.
 */
export async function getBackendUrl(): Promise<string> {
  if (cachedBackendUrl === null) {
    cachedBackendUrl = await invoke<string>('get_backend_url');
  }
  return cachedBackendUrl;
}

/** Typed wrapper for the `set_backend_url` command. */
export async function setBackendUrl(url: string): Promise<void> {
  await invoke<void>('set_backend_url', { url });
  cachedBackendUrl = null;
}

/** Typed wrapper for the `backup_database` command. */
export function backupDatabase(path?: string): Promise<string> {
  return invoke<string>('backup_database', { path: path ?? null });
}

/** Typed wrapper for the `restore_database` command. */
export function restoreDatabase(path: string): Promise<void> {
  return invoke<void>('restore_database', { path });
}

/** Typed wrapper for the `save_export_bytes` command. */
export function saveExportBytes(name: string, bytes: number[]): Promise<string> {
  return invoke<string>('save_export_bytes', { name, bytes });
}

/** Typed wrapper for the `print_file` command. */
export function printFile(path: string): Promise<void> {
  return invoke<void>('print_file', { path });
}

/** Typed wrapper for the `local_db_status` command. */
export function localDbStatus(): Promise<LocalDbStatus> {
  return invoke<LocalDbStatus>('local_db_status');
}

/**
 * Save an exported file. In Tauri this writes the bytes through the native
 * save dialog; in a browser it falls back to the existing object-URL download.
 */
export async function downloadNative(
  name: string,
  bytes: Blob | Uint8Array | number[],
): Promise<void> {
  if (isTauri()) {
    let raw: number[];
    if (Array.isArray(bytes)) {
      raw = bytes;
    } else if (bytes instanceof Uint8Array) {
      raw = Array.from(bytes);
    } else {
      raw = Array.from(new Uint8Array(await bytes.arrayBuffer()));
    }
    await saveExportBytes(name, raw);
    return;
  }

  const blob = bytes instanceof Blob
    ? bytes
    : new Blob([
        new Uint8Array(bytes instanceof Uint8Array ? Array.from(bytes) : bytes),
      ]);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
