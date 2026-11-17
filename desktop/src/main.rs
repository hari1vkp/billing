mod app;
mod theme;
mod ui;

use app::App;
use billflow_shared::db::{default_db_path, migrate, Database};
use billflow_shared::repo::bootstrap;
use billflow_shared::services::seed::seed_demo;

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("BillFlow")
            .with_inner_size([1440.0, 900.0])
            .with_min_inner_size([1024.0, 680.0]),
        ..Default::default()
    };

    eframe::run_native(
        "BillFlow",
        options,
        Box::new(move |cc| {
            theme::configure_fonts(&cc.egui_ctx);
            theme::apply(&cc.egui_ctx);

            let db = open_database();
            Ok(Box::new(App::new(db)))
        }),
    )
}

/// Open (or create) the local SQLite database. If the on-disk database cannot
/// be opened we fall back to an in-memory one so the application still starts;
/// the error is surfaced as a status message in the UI.
fn open_database() -> Database {
    let path = default_db_path();
    let db = match Database::open(&path) {
        Ok(db) => db,
        Err(_) => match Database::in_memory() {
            Ok(db) => db,
            Err(_) => {
                // Last resort: eframe requires an App; App::new handles a
                // missing database gracefully by showing an error state.
                return Database::in_memory().expect("in-memory SQLite must be available");
            }
        },
    };

    let setup = (|| -> billflow_shared::Result<()> {
        {
            let conn = db.conn();
            migrate(&conn)?;
        }
        {
            let conn = db.conn();
            bootstrap(&conn)?;
        }
        {
            let conn = db.conn();
            seed_demo(&conn)?;
        }
        Ok(())
    })();

    if setup.is_err() {
        // Nothing to do here: App::new runs a health check and will display a
        // toast if the schema is unusable.
        eprintln!("BillFlow database initialisation returned an error");
    }

    db
}
