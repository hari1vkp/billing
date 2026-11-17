//! Owner console: sidebar shell, dashboard, tables and management forms.

use billflow_shared::auth;
use billflow_shared::db::app_data_dir;
use billflow_shared::models::{
    ActivityLog, Business, Customer, CustomerStats, Invoice, InvoiceDetail, InvoiceItem,
    InvoiceStatus, Payment, Product, Role, StockMovement, User,
};
use billflow_shared::repo;
use billflow_shared::services::analytics::{self, Analytics, TrendPoint};
use billflow_shared::services::inventory;
use billflow_shared::services::payments;
use billflow_shared::services::reports;
use egui::{
    Align, Context, FontId, Frame, Layout, Margin, CornerRadius, Sense, Stroke, TextEdit, Ui, Vec2,
};

use crate::app::{empty_analytics, App, Screen};
use crate::theme::*;
use crate::ui::widgets as w;

const PAGE_SIZE: i64 = 12;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum AdminPage {
    Overview,
    Billing,
    Inventory,
    Customers,
    Payments,
    Analytics,
    Staff,
    Activity,
    Settings,
}

impl AdminPage {
    fn label(self) -> &'static str {
        match self {
            AdminPage::Overview => "Overview",
            AdminPage::Billing => "Billing",
            AdminPage::Inventory => "Inventory",
            AdminPage::Customers => "Customers",
            AdminPage::Payments => "Payments",
            AdminPage::Analytics => "Analytics",
            AdminPage::Staff => "Staff",
            AdminPage::Activity => "Activity",
            AdminPage::Settings => "Settings",
        }
    }

    fn subtitle(self) -> &'static str {
        match self {
            AdminPage::Overview => "A snapshot of your business today",
            AdminPage::Billing => "Create, manage and track every invoice",
            AdminPage::Inventory => "Products, stock levels and movements",
            AdminPage::Customers => "Your contacts, history and relationships",
            AdminPage::Payments => "Collections, confirmations and reconciliation",
            AdminPage::Analytics => "Understand performance and spot trends",
            AdminPage::Staff => "Manage team access and roles",
            AdminPage::Activity => "A record of everything that happened",
            AdminPage::Settings => "Business profile, UPI and team access",
        }
    }

    const ALL: [AdminPage; 9] = [
        AdminPage::Overview,
        AdminPage::Billing,
        AdminPage::Inventory,
        AdminPage::Customers,
        AdminPage::Payments,
        AdminPage::Analytics,
        AdminPage::Staff,
        AdminPage::Activity,
        AdminPage::Settings,
    ];
}

#[derive(Clone, Debug, Default)]
pub struct ProductForm {
    pub id: Option<String>,
    pub name: String,
    pub sku: String,
    pub description: String,
    pub hsn_code: String,
    pub barcode: String,
    pub price: String,
    pub gst_rate: String,
    pub stock: String,
    pub low_stock_threshold: String,
    pub track_inventory: bool,
    pub is_service: bool,
}

#[derive(Clone, Debug, Default)]
pub struct CustomerForm {
    pub id: Option<String>,
    pub name: String,
    pub phone: String,
    pub email: String,
    pub address: String,
    pub city: String,
    pub state: String,
    pub pincode: String,
    pub gstin: String,
    pub notes: String,
}

#[derive(Clone, Debug)]
pub struct BusinessForm {
    pub name: String,
    pub legal_name: String,
    pub email: String,
    pub phone: String,
    pub address: String,
    pub city: String,
    pub state: String,
    pub pincode: String,
    pub gstin: String,
    pub upi_id: String,
    pub upi_name: String,
    pub currency: String,
    pub invoice_prefix: String,
    pub invoice_footer: String,
    pub default_gst_rate: String,
    pub low_stock_threshold: String,
}

impl Default for BusinessForm {
    fn default() -> Self {
        Self {
            name: String::new(),
            legal_name: String::new(),
            email: String::new(),
            phone: String::new(),
            address: String::new(),
            city: String::new(),
            state: String::new(),
            pincode: String::new(),
            gstin: String::new(),
            upi_id: String::new(),
            upi_name: String::new(),
            currency: "INR".to_string(),
            invoice_prefix: "INV".to_string(),
            invoice_footer: String::new(),
            default_gst_rate: "18".to_string(),
            low_stock_threshold: "10".to_string(),
        }
    }
}

impl BusinessForm {
    fn from_business(b: &Business) -> Self {
        Self {
            name: b.name.clone(),
            legal_name: b.legal_name.clone().unwrap_or_default(),
            email: b.email.clone(),
            phone: b.phone.clone(),
            address: b.address.clone(),
            city: b.city.clone(),
            state: b.state.clone(),
            pincode: b.pincode.clone(),
            gstin: b.gstin.clone(),
            upi_id: b.upi_id.clone(),
            upi_name: b.upi_name.clone(),
            currency: b.currency.clone(),
            invoice_prefix: b.invoice_prefix.clone(),
            invoice_footer: b.invoice_footer.clone().unwrap_or_default(),
            default_gst_rate: format!("{}", b.default_gst_rate),
            low_stock_threshold: format!("{}", b.low_stock_threshold),
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct StaffForm {
    pub full_name: String,
    pub email: String,
    pub phone: String,
    pub password: String,
    pub is_owner: bool,
}

pub struct AdminState {
    pub refresh_needed: bool,
    pub page: AdminPage,
    pub analytics: Option<Analytics>,

    pub invoice_query: String,
    pub invoice_status: String,
    pub invoice_offset: i64,
    pub invoices: Vec<Invoice>,
    pub invoice_total: i64,
    pub selected_invoice_id: Option<String>,
    pub invoice_detail: Option<InvoiceDetail>,

    pub product_query: String,
    pub low_stock_only: bool,
    pub product_offset: i64,
    pub products: Vec<Product>,
    pub product_total: i64,
    pub product_form: Option<ProductForm>,
    pub adjust_product_id: Option<String>,
    pub adjust_delta: String,
    pub adjust_reason: String,
    pub adjust_notes: String,
    pub movement_offset: i64,
    pub movement_product_id: Option<String>,
    pub movements: Vec<StockMovement>,
    pub movement_total: i64,

    pub customer_query: String,
    pub customer_offset: i64,
    pub customers: Vec<Customer>,
    pub customer_total: i64,
    pub customer_form: Option<CustomerForm>,
    pub selected_customer_id: Option<String>,
    pub customer_stats: Option<CustomerStats>,
    pub interactions: Vec<(String, String, String)>,
    pub interaction_text: String,

    pub payment_query: String,
    pub payment_status: String,
    pub payment_offset: i64,
    pub payments: Vec<Payment>,
    pub payment_total: i64,
    pub confirm_payment_id: Option<String>,
    pub confirm_reference: String,

    pub analytics_from: String,
    pub analytics_to: String,

    pub staff: Vec<User>,
    pub staff_form: Option<StaffForm>,

    pub activity_category: String,
    pub activity_query: String,
    pub activity_offset: i64,
    pub activities: Vec<ActivityLog>,
    pub activity_total: i64,

    pub business_form: BusinessForm,
}

impl Default for AdminState {
    fn default() -> Self {
        Self {
            refresh_needed: false,
            page: AdminPage::Overview,
            analytics: None,
            invoice_query: String::new(),
            invoice_status: "all".to_string(),
            invoice_offset: 0,
            invoices: Vec::new(),
            invoice_total: 0,
            selected_invoice_id: None,
            invoice_detail: None,
            product_query: String::new(),
            low_stock_only: false,
            product_offset: 0,
            products: Vec::new(),
            product_total: 0,
            product_form: None,
            adjust_product_id: None,
            adjust_delta: String::new(),
            adjust_reason: "correction".to_string(),
            adjust_notes: String::new(),
            movement_offset: 0,
            movement_product_id: None,
            movements: Vec::new(),
            movement_total: 0,
            customer_query: String::new(),
            customer_offset: 0,
            customers: Vec::new(),
            customer_total: 0,
            customer_form: None,
            selected_customer_id: None,
            customer_stats: None,
            interactions: Vec::new(),
            interaction_text: String::new(),
            payment_query: String::new(),
            payment_status: "all".to_string(),
            payment_offset: 0,
            payments: Vec::new(),
            payment_total: 0,
            confirm_payment_id: None,
            confirm_reference: String::new(),
            analytics_from: String::new(),
            analytics_to: String::new(),
            staff: Vec::new(),
            staff_form: None,
            activity_category: "all".to_string(),
            activity_query: String::new(),
            activity_offset: 0,
            activities: Vec::new(),
            activity_total: 0,
            business_form: BusinessForm::default(),
        }
    }
}

/* ------------------------------- shell ----------------------------------- */

pub fn shell(app: &mut App, ctx: &Context) {
    egui::SidePanel::left("admin_sidebar")
        .exact_width(248.0)
        .resizable(false)
        .frame(Frame::new().fill(INK))
        .show(ctx, |ui| sidebar(app, ui));

    egui::CentralPanel::default()
        .frame(Frame::new().fill(CANVAS))
        .show(ctx, |ui| {
            topbar(app, ui);
            egui::ScrollArea::vertical()
                .id_salt("admin_content")
                .auto_shrink([false, false])
                .show(ui, |ui| {
                    ui.add_space(27.0);
                    ui.horizontal(|ui| {
                        ui.add_space(32.0);
                        ui.allocate_ui(Vec2::new(ui.available_width() - 64.0, 1.0), |ui| {
                            page_content(app, ui);
                        });
                        ui.add_space(32.0);
                    });
                    ui.add_space(40.0);
                });
        });
}

fn sidebar(app: &mut App, ui: &mut Ui) {
    ui.vertical(|ui| {
        ui.add_space(18.0);
        ui.horizontal(|ui| {
            ui.add_space(20.0);
            Frame::new()
                .fill(ORANGE)
                .corner_radius(CornerRadius::same(9))
                .inner_margin(Margin::symmetric(8, 7))
                .show(ui, |ui| {
                    ui.label(egui::RichText::new("▤").size(17.0).color(WHITE).strong());
                });
            ui.add_space(10.0);
            ui.vertical(|ui| {
                ui.label(egui::RichText::new("BillFlow").size(17.0).color(ON_DARK).strong());
                ui.label(egui::RichText::new("Billing made simple").size(10.0).color(ON_DARK_MUTED));
            });
        });
        ui.add_space(24.0);
        ui.label(
            egui::RichText::new("  WORKSPACE")
                .size(10.0)
                .color(ON_DARK_MUTED)
                .strong(),
        );
        ui.add_space(8.0);

        ui.vertical(|ui| {
            for page in AdminPage::ALL {
                let active = app.admin.page == page;
                let (fill, color) = if active {
                    (ORANGE, WHITE)
                } else {
                    (egui::Color32::TRANSPARENT, ON_DARK)
                };
                let button = ui.add_sized(
                    [ui.available_width() - 24.0, 36.0],
                    egui::Button::new(
                        egui::RichText::new(page.label()).size(13.0).color(color).strong(),
                    )
                    .fill(fill)
                    .stroke(Stroke::NONE)
                    .corner_radius(CornerRadius::same(RADIUS)),
                );
                if button.clicked() {
                    app.admin.page = page;
                    app.admin.selected_invoice_id = None;
                    app.admin.invoice_detail = None;
                    app.admin.product_form = None;
                    app.admin.customer_form = None;
                    app.admin.selected_customer_id = None;
                    app.admin.refresh_needed = true;
                }
            }
        });

        ui.add_space(20.0);
        ui.with_layout(Layout::bottom_up(Align::LEFT), |ui| {
            ui.vertical_centered(|ui| {
                ui.label(egui::RichText::new("BillFlow v1.0").size(10.5).color(ON_DARK_MUTED));
            });
            ui.add_space(12.0);
            Frame::new()
                .fill(egui::Color32::from_rgba_unmultiplied(0xF7, 0xF5, 0xF0, 20))
                .corner_radius(CornerRadius::same(10))
                .inner_margin(Margin::same(10))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        Frame::new()
                            .fill(egui::Color32::from_rgba_unmultiplied(0xFF, 0x6A, 0x00, 46))
                            .corner_radius(CornerRadius::same(8))
                            .inner_margin(Margin::same(7))
                            .show(ui, |ui| {
                                ui.label(egui::RichText::new("▣").size(13.0).color(ORANGE));
                            });
                        ui.add_space(8.0);
                        ui.vertical(|ui| {
                            let name = app.business.as_ref().map(|b| b.name.clone())
                                .unwrap_or_else(|| "My Business".to_string());
                            ui.label(egui::RichText::new(truncate(&name, 20)).size(11.5).color(ON_DARK).strong());
                            let role = if app.is_owner() { "owner" } else { "staff" };
                            ui.label(egui::RichText::new(format!("{} · {}", app.currency(), role)).size(10.0).color(ON_DARK_MUTED));
                        });
                    });
                });
        });
    });
}

fn topbar(app: &mut App, ui: &mut Ui) {
    ui.add_space(19.0);
    ui.horizontal(|ui| {
        ui.add_space(32.0);
        ui.vertical(|ui| {
            ui.label(egui::RichText::new(app.admin.page.label()).size(16.0).color(INK).strong());
            ui.label(egui::RichText::new(app.admin.page.subtitle()).size(11.0).color(MUTED));
        });
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if w::ghost(ui, "Sign out").clicked() {
                app.logout();
                return;
            }
            let name = app.user.as_ref().map(|u| u.full_name.clone()).unwrap_or_default();
            ui.label(egui::RichText::new(name).size(12.0).color(INK));
            ui.add_space(6.0);
            if w::primary(ui, "Open POS").clicked() {
                app.open_pos();
            }
        });
        ui.add_space(32.0);
    });
    ui.add_space(15.0);
    let rect = ui.available_rect_before_wrap();
    ui.painter().line_segment(
        [egui::pos2(rect.left(), rect.top()), egui::pos2(rect.right(), rect.top())],
        Stroke::new(1.0_f32, BORDER),
    );
    ui.add_space(2.0);
}

fn page_content(app: &mut App, ui: &mut Ui) {
    match app.admin.page {
        AdminPage::Overview => overview(app, ui),
        AdminPage::Billing => billing(app, ui),
        AdminPage::Inventory => inventory(app, ui),
        AdminPage::Customers => customers(app, ui),
        AdminPage::Payments => payments_page(app, ui),
        AdminPage::Analytics => analytics_page(app, ui),
        AdminPage::Staff => staff(app, ui),
        AdminPage::Activity => activity(app, ui),
        AdminPage::Settings => settings(app, ui),
    }
}

/* ------------------------------ data loading ------------------------------ */

pub fn reload(app: &mut App, _ctx: &Context) {
    if !app.is_owner() {
        app.screen = Screen::Pos;
        return;
    }
    app.admin.refresh_needed = false;
    if let Some(business) = &app.business {
        app.admin.business_form = BusinessForm::from_business(business);
    }
    match app.admin.page {
        AdminPage::Overview => load_analytics(app, None),
        AdminPage::Billing => load_invoices(app),
        AdminPage::Inventory => {
            load_products(app);
            load_movements(app);
        }
        AdminPage::Customers => load_customers(app),
        AdminPage::Payments => load_payments(app),
        AdminPage::Analytics => {
            let from = if app.admin.analytics_from.trim().is_empty() { None } else { Some(app.admin.analytics_from.trim().to_string()) };
            let to = if app.admin.analytics_to.trim().is_empty() { None } else { Some(app.admin.analytics_to.trim().to_string()) };
            load_analytics(app, Some((from, to)));
        }
        AdminPage::Staff => load_staff(app),
        AdminPage::Activity => load_activity(app),
        AdminPage::Settings => {}
    }
}

fn business_id(app: &App) -> String {
    app.business_id().unwrap_or_default()
}

pub fn load_analytics(app: &mut App, range: Option<(Option<String>, Option<String>)>) {
    let bid = business_id(app);
    let from = range.as_ref().and_then(|r| r.0.as_deref());
    let to = range.as_ref().and_then(|r| r.1.as_deref());
    let result = {
        let conn = app.db.conn();
        analytics::load(&conn, &bid, from, to)
    };
    match result {
        Ok(data) => app.admin.analytics = Some(data),
        Err(e) => {
            app.admin.analytics = Some(empty_analytics());
            app.show_error("Could not load analytics", e);
        }
    }
}

pub fn load_invoices(app: &mut App) {
    let bid = business_id(app);
    let query = app.admin.invoice_query.clone();
    let status = if app.admin.invoice_status == "all" { String::new() } else { app.admin.invoice_status.clone() };
    let offset = app.admin.invoice_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_invoices(&conn, &bid, &query, &status, PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.invoices = items;
            app.admin.invoice_total = total;
        }
        Err(e) => app.show_error("Could not load invoices", e),
    }
}

pub fn load_products(app: &mut App) {
    let bid = business_id(app);
    let query = app.admin.product_query.clone();
    let low = app.admin.low_stock_only;
    let offset = app.admin.product_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_products(&conn, &bid, &query, low, PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.products = items;
            app.admin.product_total = total;
        }
        Err(e) => app.show_error("Could not load products", e),
    }
}

pub fn load_movements(app: &mut App) {
    let bid = business_id(app);
    let product_id = app.admin.movement_product_id.clone();
    let offset = app.admin.movement_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_movements(&conn, &bid, product_id.as_deref(), PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.movements = items;
            app.admin.movement_total = total;
        }
        Err(e) => app.show_error("Could not load stock movements", e),
    }
}

pub fn load_customers(app: &mut App) {
    let bid = business_id(app);
    let query = app.admin.customer_query.clone();
    let offset = app.admin.customer_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_customers(&conn, &bid, &query, PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.customers = items;
            app.admin.customer_total = total;
        }
        Err(e) => app.show_error("Could not load customers", e),
    }
}

pub fn load_payments(app: &mut App) {
    let bid = business_id(app);
    let query = app.admin.payment_query.clone();
    let status = if app.admin.payment_status == "all" { String::new() } else { app.admin.payment_status.clone() };
    let offset = app.admin.payment_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_payments(&conn, &bid, &query, &status, PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.payments = items;
            app.admin.payment_total = total;
        }
        Err(e) => app.show_error("Could not load payments", e),
    }
}

pub fn load_staff(app: &mut App) {
    let bid = business_id(app);
    let result = {
        let conn = app.db.conn();
        auth::list_users(&conn, &bid)
    };
    match result {
        Ok(users) => app.admin.staff = users,
        Err(e) => app.show_error("Could not load staff", e),
    }
}

pub fn load_activity(app: &mut App) {
    let bid = business_id(app);
    let category = if app.admin.activity_category == "all" { String::new() } else { app.admin.activity_category.clone() };
    let query = app.admin.activity_query.clone();
    let offset = app.admin.activity_offset;
    let result = {
        let conn = app.db.conn();
        repo::list_activity(&conn, &bid, &category, &query, PAGE_SIZE, offset)
    };
    match result {
        Ok((items, total)) => {
            app.admin.activities = items;
            app.admin.activity_total = total;
        }
        Err(e) => app.show_error("Could not load activity", e),
    }
}

/* ------------------------------- overview -------------------------------- */

fn overview(app: &mut App, ui: &mut Ui) {
    let data = app.admin.analytics.clone().unwrap_or_else(empty_analytics);
    let currency = app.currency();

    ui.horizontal(|ui| {
        ui.label(egui::RichText::new("Dashboard overview").size(21.0).color(INK).strong());
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            w::badge(ui, format!("{}% growth", data.growth_percent), true);
            if w::secondary(ui, "New invoice").clicked() {
                app.admin.page = AdminPage::Billing;
                app.admin.refresh_needed = true;
            }
        });
    });
    w::muted(ui, "Here's what's happening across your business today");
    ui.add_space(18.0);

    let total_sales = app.money(data.today_sales);
    let collections = app.money(data.month_collections);
    let month_sales = app.money(data.month_sales);
    let outstanding = app.money(data.outstanding);
    let year_sales = app.money(data.year_sales);
    let txn_hint = format!("{} transactions today", data.today_transactions);
    let year_hint = format!("{} this year", year_sales);
    let pending_hint = format!("{} invoices pending", data.pending_invoices);
    let low_stock = format!("{}", data.low_stock);
    let total_customers = format!("{}", data.total_customers);
    let active_hint = format!("{} active customers", data.active_customers);
    kpi_row(ui, &[
        ("Today's Sales", total_sales.as_str(), txn_hint.as_str()),
        ("Collections", collections.as_str(), "Cash received this month"),
        ("This Month's Sales", month_sales.as_str(), year_hint.as_str()),
        ("Outstanding", outstanding.as_str(), pending_hint.as_str()),
        ("Low Stock", low_stock.as_str(), "Items need restocking"),
        ("Customers", total_customers.as_str(), active_hint.as_str()),
    ]);
    ui.add_space(18.0);

    ui.horizontal(|ui| {
        let total = ui.available_width();
        let left = (total - 18.0) * 0.66;
        ui.allocate_ui(Vec2::new(left, ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Sales & Collections", Some("How revenue is tracking over time"));
                ui.add_space(12.0);
                trend_chart(ui, &data.sales_trend);
                ui.add_space(10.0);
                chart_legend(ui);
            });
        });
        ui.add_space(18.0);
        ui.allocate_ui(Vec2::new(ui.available_width(), ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Payment Methods", Some("Share of collections"));
                ui.add_space(12.0);
                method_chart(ui, &data.methods);
            });
        });
    });
    ui.add_space(18.0);

    ui.horizontal(|ui| {
        let total = ui.available_width();
        ui.allocate_ui(Vec2::new((total - 18.0) * 0.5, ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Top Products", Some("Best sellers by revenue"));
                ui.add_space(10.0);
                if data.top_products.is_empty() {
                    w::empty_state(ui, "No product sales yet", "Sales appear here once you create invoices.");
                } else {
                    table(ui, &["Product", "Qty", "Revenue"], data.top_products.iter().take(5).map(|p| {
                        vec![p.name.clone(), format!("{}", p.quantity), app.money(p.revenue)]
                    }));
                }
            });
        });
        ui.add_space(18.0);
        ui.allocate_ui(Vec2::new(ui.available_width(), ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Recent Invoices", Some("Latest billing activity"));
                ui.add_space(10.0);
                if data.recent_invoices.is_empty() {
                    w::empty_state(ui, "No invoices yet", "Create your first invoice to get started.");
                } else {
                    table(ui, &["Invoice", "Customer", "Amount", "Status"], data.recent_invoices.iter().take(5).map(|inv| {
                        vec![inv.invoice_number.clone(), inv.customer_name.clone().unwrap_or_else(|| "—".to_string()), app.money(inv.total_amount), status_label(&inv.status).to_string()]
                    }));
                }
            });
        });
    });
    ui.add_space(18.0);

    w::flat_card(ui, |ui| {
        w::section_title(ui, "Recent Payments", Some("The latest collections recorded"));
        ui.add_space(10.0);
        if data.recent_payments.is_empty() {
            w::empty_state(ui, "No payments yet", "Recorded payments will show up here.");
        } else {
            table(ui, &["Customer", "Invoice", "Method", "Amount", "Status"], data.recent_payments.iter().take(6).map(|p| {
                vec![p.customer_name.clone().unwrap_or_else(|| "—".to_string()), p.invoice_number.clone().unwrap_or_else(|| "—".to_string()), method_label(&p.method).to_string(), app.money(p.amount), p.status.clone()]
            }));
        }
    });
    let _ = currency;
}

fn kpi_row(ui: &mut Ui, items: &[(&str, &str, &str)]) {
    let spacing = 14.0;
    let width = (ui.available_width() - spacing * (items.len() - 1) as f32) / items.len() as f32;
    ui.horizontal(|ui| {
        for (label, value, hint) in items {
            ui.allocate_ui(Vec2::new(width, 110.0), |ui| {
                w::card(ui, |ui| {
                    w::caption(ui, *label);
                    ui.add_space(8.0);
                    ui.label(egui::RichText::new(*value).size(17.0).color(INK).strong());
                    ui.add_space(5.0);
                    w::caption(ui, *hint);
                });
            });
        }
    });
}

fn trend_chart(ui: &mut Ui, points: &[TrendPoint]) {
    if points.is_empty() {
        w::empty_state(ui, "No trend data", "Sales will appear here after your first sale.");
        return;
    }
    let (rect, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 170.0), Sense::hover());
    let painter = ui.painter();
    let max = points.iter().fold(1.0f64, |m, p| m.max(p.sales).max(p.collections));
    let base = rect.bottom() - 22.0;
    let top = rect.top() + 10.0;
    painter.line_segment(
        [egui::pos2(rect.left(), base), egui::pos2(rect.right(), base)],
        Stroke::new(1.0_f32, BORDER),
    );
    let slot = rect.width() / points.len() as f32;
    let bar_w = (slot * 0.30).min(22.0);
    for (i, point) in points.iter().enumerate() {
        let cx = rect.left() + slot * i as f32 + slot / 2.0;
        let sh = ((point.sales / max) * (base - top) as f64) as f32;
        let ch = ((point.collections / max) * (base - top) as f64) as f32;
        painter.rect_filled(
            egui::Rect::from_min_max(
                egui::pos2(cx - bar_w - 1.0, base - sh),
                egui::pos2(cx - 1.0, base),
            ),
            CornerRadius::same(2),
            INK,
        );
        painter.rect_filled(
            egui::Rect::from_min_max(
                egui::pos2(cx + 1.0, base - ch),
                egui::pos2(cx + bar_w + 1.0, base),
            ),
            CornerRadius::same(2),
            MUTED,
        );
        painter.text(
            egui::pos2(cx, base + 5.0),
            egui::Align2::CENTER_TOP,
            truncate(&point.period, 7),
            FontId::new(9.5, egui::FontFamily::Proportional),
            MUTED,
        );
    }
}

fn chart_legend(ui: &mut Ui) {
    ui.horizontal(|ui| {
        ui.label(egui::RichText::new("■").size(10.0).color(INK));
        w::caption(ui, "Sales");
        ui.add_space(10.0);
        ui.label(egui::RichText::new("■").size(10.0).color(MUTED));
        w::caption(ui, "Collections");
    });
}

fn method_chart(ui: &mut Ui, methods: &[analytics::MethodRow]) {
    if methods.is_empty() {
        w::empty_state(ui, "No payment data", "Collections appear here after a sale.");
        return;
    }
    let total: f64 = methods.iter().map(|m| m.amount).sum();
    for method in methods {
        w::caption(ui, format!("{}  ·  {}", method.method, method.count));
        ui.add_space(3.0);
        let (rect, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 10.0), Sense::hover());
        let fraction = if total > 0.0 { method.amount / total } else { 0.0 };
        ui.painter().rect_filled(rect, CornerRadius::same(3), SUBTLE);
        let fill_w = rect.width() * fraction as f32;
        if fill_w > 0.5 {
            ui.painter().rect_filled(
                egui::Rect::from_min_size(rect.min, Vec2::new(fill_w, rect.height())),
                CornerRadius::same(3),
                INK,
            );
        }
        ui.add_space(7.0);
        ui.label(w::money_text(method.amount, 12.0, INK));
        ui.add_space(9.0);
    }
}

fn method_label(method: &billflow_shared::models::PaymentMethod) -> &'static str {
    use billflow_shared::models::PaymentMethod;
    match method {
        PaymentMethod::Upi => "UPI",
        PaymentMethod::Cash => "Cash",
    }
}

fn status_label(status: &InvoiceStatus) -> &'static str {
    match status {
        InvoiceStatus::Draft => "Draft",
        InvoiceStatus::Unpaid => "Unpaid",
        InvoiceStatus::PartiallyPaid => "Partially paid",
        InvoiceStatus::Paid => "Paid",
        InvoiceStatus::Cancelled => "Cancelled",
    }
}

fn status_from_str(text: &str) -> Option<InvoiceStatus> {
    match text {
        "draft" => Some(InvoiceStatus::Draft),
        "unpaid" => Some(InvoiceStatus::Unpaid),
        "partially_paid" | "partially paid" => Some(InvoiceStatus::PartiallyPaid),
        "paid" => Some(InvoiceStatus::Paid),
        "cancelled" => Some(InvoiceStatus::Cancelled),
        _ => None,
    }
}

fn status_key(status: &InvoiceStatus) -> &'static str {
    match status {
        InvoiceStatus::Draft => "draft",
        InvoiceStatus::Unpaid => "unpaid",
        InvoiceStatus::PartiallyPaid => "partially_paid",
        InvoiceStatus::Paid => "paid",
        InvoiceStatus::Cancelled => "cancelled",
    }
}

fn table<I, R>(ui: &mut Ui, headers: &[&str], rows: I)
where
    I: Iterator<Item = R>,
    R: IntoIterator<Item = String>,
{
    egui::Grid::new(format!("table_{}_{}", headers.len(), ui.id().value()))
        .num_columns(headers.len())
        .striped(true)
        .spacing([12.0, 7.0])
        .show(ui, |ui| {
            for header in headers {
                ui.label(egui::RichText::new(*header).size(11.0).color(MUTED).strong());
            }
            ui.end_row();
            for row in rows {
                for (index, cell) in row.into_iter().enumerate() {
                    ui.label(egui::RichText::new(cell).size(12.0).color(INK));
                    let _ = index;
                }
                ui.end_row();
            }
        });
}

/* -------------------------------- billing -------------------------------- */

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn billing(app: &mut App, ui: &mut Ui) {
    if let Some(id) = app.admin.selected_invoice_id.clone() {
        invoice_detail(app, ui, &id);
        return;
    }

    w::page_header(ui, "Billing & Invoices", "Create, manage and track every invoice");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            if w::secondary(ui, "Search").clicked() {
                app.admin.invoice_offset = 0;
                load_invoices(app);
            }
            ui.add_sized(
                [ui.available_width() - 200.0, 32.0],
                TextEdit::singleline(&mut app.admin.invoice_query).hint_text("Search invoices…"),
            );
            egui::ComboBox::from_id_source("invoice_status_filter")
                .selected_text(format!("Status: {}", app.admin.invoice_status))
                .show_ui(ui, |ui| {
                    for option in ["all", "draft", "unpaid", "partially_paid", "paid", "cancelled"] {
                        ui.selectable_value(&mut app.admin.invoice_status, option.to_string(), option);
                    }
                });
        });
        ui.add_space(10.0);
        ui.separator();

        if app.admin.invoices.is_empty() {
            w::empty_state(ui, "No invoices yet", "Sales created from the POS appear here.");
        } else {
            let invoices = app.admin.invoices.clone();
            table(ui, &["Invoice", "Customer", "Date", "Amount", "Status", ""], invoices.iter().map(|inv| {
                vec![
                    inv.invoice_number.clone(),
                    inv.customer_name.clone().unwrap_or_else(|| "—".to_string()),
                    inv.issue_date.clone(),
                    app.money(inv.total_amount),
                    status_label(&inv.status).to_string(),
                    "View".to_string(),
                ]
            }));
            let ids: Vec<String> = invoices.iter().map(|i| i.id.clone()).collect();
            for id in ids {
                // Invisible row buttons are avoided here; the View cells above
                // are informational. A click anywhere on the table's status is
                // handled by the compact action list below.
                let _ = id;
            }
            ui.add_space(6.0);
            for inv in invoices.iter().take(PAGE_SIZE as usize) {
                ui.horizontal(|ui| {
                    w::muted(ui, &inv.invoice_number);
                    if w::link(ui, "Open invoice").clicked() {
                        app.admin.selected_invoice_id = Some(inv.id.clone());
                        open_invoice(app, &inv.id);
                    }
                });
            }
        }
        if w::pagination(
            ui,
            &mut app.admin.invoice_offset,
            PAGE_SIZE,
            app.admin.invoice_total,
            "invoices",
        ) {
            load_invoices(app);
        }
    });
}

fn open_invoice(app: &mut App, id: &str) {
    let bid = business_id(app);
    let result = {
        let conn = app.db.conn();
        repo::get_invoice(&conn, &bid, id)
    };
    match result {
        Ok(detail) => app.admin.invoice_detail = Some(detail),
        Err(e) => app.show_error("Could not open invoice", e),
    }
}

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn invoice_detail(app: &mut App, ui: &mut Ui, id: &str) {
    if app.admin.invoice_detail.as_ref().map(|d| d.invoice.id.clone()).as_deref() != Some(id) {
        open_invoice(app, id);
    }
    let Some(detail) = app.admin.invoice_detail.clone() else {
        w::empty_state(ui, "Loading invoice", "Please wait…");
        return;
    };
    let invoice = &detail.invoice;

    if w::secondary(ui, "←  All invoices").clicked() {
        app.admin.selected_invoice_id = None;
        app.admin.invoice_detail = None;
    }
    ui.add_space(12.0);
    ui.label(
        egui::RichText::new(&invoice.invoice_number)
            .size(21.0)
            .color(INK)
            .strong(),
    );
    w::muted(ui, format!("Issued {} · {}", invoice.issue_date, status_label(&invoice.status)));
    ui.add_space(14.0);

    w::card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                w::caption(ui, "Customer");
                ui.label(egui::RichText::new(invoice.customer_name.clone().unwrap_or_else(|| "Walk-in Customer".to_string())).size(13.0).color(INK).strong());
            });
            ui.add_space(40.0);
            ui.vertical(|ui| {
                w::caption(ui, "Total");
                ui.label(w::money_text(invoice.total_amount, 17.0, INK));
            });
            ui.add_space(40.0);
            ui.vertical(|ui| {
                w::caption(ui, "Paid");
                ui.label(w::money_text(invoice.paid_amount, 17.0, INK));
            });
            ui.add_space(40.0);
            ui.vertical(|ui| {
                w::caption(ui, "Balance");
                ui.label(w::money_text(invoice.balance_amount, 17.0, INK));
            });
        });
        ui.add_space(12.0);
        ui.separator();
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            w::caption(ui, "Change status");
            let mut current = status_key(&invoice.status).to_string();
            egui::ComboBox::from_id_source("invoice_status_change")
                .selected_text(status_label(&invoice.status))
                .show_ui(ui, |ui| {
                    for key in ["draft", "unpaid", "partially_paid", "paid", "cancelled"] {
                        ui.selectable_value(&mut current, key.to_string(), key.replace('_', " "));
                    }
                });
            if w::secondary(ui, "Update").clicked() {
                if let Some(status) = status_from_str(&current) {
                    let bid = business_id(app);
                    let uid = app.user_id().unwrap_or_default();
                    let result = {
                        let conn = app.db.conn();
                        repo::set_invoice_status(&conn, &bid, id, status, Some(&uid))
                    };
                    match result {
                        Ok(_) => {
                            app.set_status("Invoice status updated", false);
                            open_invoice(app, id);
                            load_invoices(app);
                        }
                        Err(e) => app.show_error("Could not update invoice", e),
                    }
                }
            }
            if w::ghost(ui, "Cancel invoice").clicked() {
                let bid = business_id(app);
                let uid = app.user_id().unwrap_or_default();
                let result = {
                    let conn = app.db.conn();
                    repo::set_invoice_status(&conn, &bid, id, InvoiceStatus::Cancelled, Some(&uid))
                };
                match result {
                    Ok(_) => {
                        app.set_status("Invoice cancelled", false);
                        open_invoice(app, id);
                        load_invoices(app);
                    }
                    Err(e) => app.show_error("Could not cancel invoice", e),
                }
            }
        });
        ui.add_space(8.0);
        if w::secondary(ui, "Download PDF").clicked() {
            download_invoice_pdf(app, &detail);
        }
    });
    ui.add_space(16.0);

    w::flat_card(ui, |ui| {
        w::section_title(ui, "Items", None);
        ui.add_space(8.0);
        invoice_items_table(app, ui, &detail.items);
    });
    ui.add_space(16.0);
    w::flat_card(ui, |ui| {
        w::section_title(ui, "Payments", None);
        ui.add_space(8.0);
        table(ui, &["Reference", "Method", "Amount", "Status", "Date"], detail.payments.iter().map(|p| {
            vec![p.reference.clone().unwrap_or_else(|| "—".to_string()), method_label(&p.method).to_string(), app.money(p.amount), p.status.clone(), p.payment_date.clone().unwrap_or_else(|| "—".to_string())]
        }));
    });
}

fn invoice_items_table(app: &App, ui: &mut Ui, items: &[InvoiceItem]) {
    let money = |v: f64| app.money(v);
    table(ui, &["Description", "Qty", "Rate", "Disc", "GST", "Total"], items.iter().map(|item| {
        vec![
            item.description.clone(),
            format!("{}", item.quantity),
            money(item.unit_price),
            money(item.discount_amount),
            format!("{}%", item.gst_rate),
            money(item.line_total),
        ]
    }));
}

fn download_invoice_pdf(app: &mut App, detail: &InvoiceDetail) {
    let bid = business_id(app);
    let customer = if detail.invoice.customer_id.trim().is_empty() {
        walk_in_customer(&bid)
    } else {
        let cid = &detail.invoice.customer_id;
        let result = {
            let conn = app.db.conn();
            repo::get_customer(&conn, &bid, cid)
        };
        match result {
            Ok(Some(customer)) => customer,
            _ => walk_in_customer(&bid),
        }
    };
    let Some(business) = app.business.clone() else { return };
    let result = reports::invoice_pdf(
        &business,
        &customer,
        &detail.invoice,
        &detail.items,
    );
    match result {
        Ok(bytes) => {
            if let Some(path) = save_export(&format!("invoice-{}.pdf", detail.invoice.invoice_number), &bytes) {
                app.set_status(format!("PDF saved to {}", path.display()), false);
            }
        }
        Err(e) => app.show_error("Could not create PDF", e),
    }
}

fn walk_in_customer(business_id: &str) -> Customer {
    Customer {
        id: "walk-in".to_string(),
        business_id: business_id.to_string(),
        name: "Walk-in Customer".to_string(),
        phone: String::new(),
        email: String::new(),
        address: String::new(),
        city: String::new(),
        state: String::new(),
        pincode: String::new(),
        gstin: String::new(),
        notes: None,
        is_active: true,
        created_at: String::new(),
        updated_at: String::new(),
    }
}

fn save_export(file_name: &str, bytes: &[u8]) -> Option<std::path::PathBuf> {
    let dir = app_data_dir().join("exports");
    std::fs::create_dir_all(&dir).ok()?;
    let path = dir.join(file_name);
    std::fs::write(&path, bytes).ok()?;
    Some(path)
}

/* ------------------------------- inventory ------------------------------- */

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn inventory(app: &mut App, ui: &mut Ui) {
    w::page_header(ui, "Inventory", "Products, stock levels and movements");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_sized([220.0, 32.0], TextEdit::singleline(&mut app.admin.product_query).hint_text("Search products…"));
            let low = &mut app.admin.low_stock_only;
            if ui.checkbox(low, "Low stock only").clicked() {
                app.admin.product_offset = 0;
                load_products(app);
            }
            if w::secondary(ui, "Search").clicked() {
                app.admin.product_offset = 0;
                load_products(app);
            }
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if w::primary(ui, "+  Add product").clicked() {
                    app.admin.product_form = Some(ProductForm {
                        track_inventory: true,
                        gst_rate: "18".to_string(),
                        low_stock_threshold: "10".to_string(),
                        ..Default::default()
                    });
                }
            });
        });
        ui.add_space(10.0);
        ui.separator();

        let products = app.admin.products.clone();
        if products.is_empty() {
            w::empty_state(ui, "No products found", "Add products to start billing.");
        } else {
            table(ui, &["Product", "SKU", "Barcode", "Price", "GST", "Stock", ""], products.iter().map(|p| {
                vec![p.name.clone(), p.sku.clone(), p.barcode.clone().unwrap_or_else(|| "—".to_string()), app.money(p.price), format!("{}%", p.gst_rate), if p.is_service { "Service".to_string() } else { format!("{}", p.stock) }, "Edit".to_string()]
            }));
            ui.add_space(6.0);
            for product in products.iter().take(PAGE_SIZE as usize) {
                ui.horizontal(|ui| {
                    w::muted(ui, &product.name);
                    if w::link(ui, "Edit").clicked() {
                        app.admin.product_form = Some(ProductForm {
                            id: Some(product.id.clone()),
                            name: product.name.clone(),
                            sku: product.sku.clone(),
                            description: product.description.clone(),
                            hsn_code: product.hsn_code.clone(),
                            barcode: product.barcode.clone().unwrap_or_default(),
                            price: format!("{}", product.price),
                            gst_rate: format!("{}", product.gst_rate),
                            stock: format!("{}", product.stock),
                            low_stock_threshold: format!("{}", product.low_stock_threshold),
                            track_inventory: product.track_inventory,
                            is_service: product.is_service,
                        });
                    }
                    if w::link(ui, "Adjust stock").clicked() {
                        app.admin.adjust_product_id = Some(product.id.clone());
                        app.admin.adjust_delta.clear();
                        app.admin.adjust_notes.clear();
                        app.admin.adjust_reason = "correction".to_string();
                    }
                    if !product.is_active && w::link(ui, "Archived").clicked() {
                        // Nothing to do; archived state is shown for clarity.
                    }
                });
            }
        }
        if w::pagination(ui, &mut app.admin.product_offset, PAGE_SIZE, app.admin.product_total, "products") {
            load_products(app);
        }
    });
    ui.add_space(18.0);

    w::flat_card(ui, |ui| {
        w::section_title(ui, "Stock movements", Some("A full audit trail of stock changes"));
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            let selected = app.admin.movement_product_id.clone().unwrap_or_else(|| "All products".to_string());
            egui::ComboBox::from_id_source("movement_product")
                .selected_text(selected)
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut app.admin.movement_product_id, None, "All products");
                    for product in app.admin.products.iter().take(PAGE_SIZE as usize) {
                        ui.selectable_value(&mut app.admin.movement_product_id, Some(product.id.clone()), product.name.clone());
                    }
                });
            if w::secondary(ui, "Filter").clicked() {
                app.admin.movement_offset = 0;
                load_movements(app);
            }
        });
        ui.add_space(8.0);
        let movements = app.admin.movements.clone();
        if movements.is_empty() {
            w::empty_state(ui, "No movements yet", "Stock adjustments and sales appear here.");
        } else {
            table(ui, &["Product", "Change", "Before", "After", "Reason", "By", "Date"], movements.iter().map(|m| {
                vec![m.product_name.clone(), format!("{:+.0}", m.quantity_change), format!("{}", m.quantity_before), format!("{}", m.quantity_after), m.reason.clone(), m.performed_by_name.clone(), m.created_at.clone()]
            }));
        }
        if w::pagination(ui, &mut app.admin.movement_offset, PAGE_SIZE, app.admin.movement_total, "movements") {
            load_movements(app);
        }
    });

    if app.admin.product_form.is_some() {
        product_form_modal(app, ui.ctx());
    }
    if app.admin.adjust_product_id.is_some() {
        adjust_modal(app, ui.ctx());
    }
}

fn product_form_modal(app: &mut App, ctx: &Context) {
    let Some(mut form) = app.admin.product_form.clone() else { return };
    let editing = form.id.is_some();
    let mut save = false;
    let mut cancel = false;
    egui::Window::new(if editing { "Edit product" } else { "New product" })
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(420.0);
            two_fields(ui, "Name", &mut form.name, "SKU", &mut form.sku);
            two_fields(ui, "Barcode", &mut form.barcode, "HSN code", &mut form.hsn_code);
            w::field_label(ui, "Description");
            ui.add_sized([ui.available_width(), 32.0], TextEdit::singleline(&mut form.description));
            ui.add_space(8.0);
            two_fields(ui, "Price", &mut form.price, "GST %", &mut form.gst_rate);
            two_fields(ui, "Stock", &mut form.stock, "Low stock threshold", &mut form.low_stock_threshold);
            ui.add_space(4.0);
            ui.checkbox(&mut form.track_inventory, "Track inventory");
            ui.checkbox(&mut form.is_service, "Service (no stock)");
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() { cancel = true; }
                if w::primary(ui, "Save product").clicked() { save = true; }
            });
        });
    if cancel {
        app.admin.product_form = None;
    }
    if save {
        let bid = business_id(app);
        let barcode = if form.barcode.trim().is_empty() { None } else { Some(form.barcode.trim().to_string()) };
        let input = repo::ProductInput {
            name: form.name.trim().to_string(),
            sku: form.sku.trim().to_string(),
            description: form.description.clone(),
            hsn_code: form.hsn_code.clone(),
            barcode,
            price: form.price.parse().unwrap_or(0.0),
            gst_rate: form.gst_rate.parse().unwrap_or(0.0),
            stock: form.stock.parse().unwrap_or(0.0),
            track_inventory: form.track_inventory,
            is_service: form.is_service,
            low_stock_threshold: form.low_stock_threshold.parse().unwrap_or(0.0),
        };
        let result = {
            let conn = app.db.conn();
            match &form.id {
                Some(id) => repo::update_product(&conn, &bid, id, &input).map(|_| ()),
                None => repo::insert_product(&conn, &bid, &input).map(|_| ()),
            }
        };
        match result {
            Ok(_) => {
                app.set_status(if editing { "Product updated" } else { "Product created" }, false);
                app.admin.product_form = None;
                load_products(app);
                app.pos.refresh_needed = true;
            }
            Err(e) => app.show_error("Could not save product", e),
        }
    }
}

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn adjust_modal(app: &mut App, ctx: &Context) {
    let Some(product_id) = app.admin.adjust_product_id.clone() else { return };
    let product_name = app.admin.products.iter().find(|p| p.id == product_id)
        .map(|p| p.name.clone()).unwrap_or_else(|| "Product".to_string());
    let mut close = false;
    let mut apply = false;
    egui::Window::new("Adjust stock")
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(340.0);
            ui.label(egui::RichText::new(product_name).size(15.0).color(INK).strong());
            ui.add_space(10.0);
            w::field_label(ui, "Change (+ add / − remove)");
            ui.add_sized([ui.available_width(), 32.0], TextEdit::singleline(&mut app.admin.adjust_delta).hint_text("e.g. -5"));
            ui.add_space(6.0);
            w::field_label(ui, "Reason");
            egui::ComboBox::from_id_source("admin_stock_reason")
                .selected_text(app.admin.adjust_reason.clone())
                .show_ui(ui, |ui| {
                    for reason in ["found", "damaged", "return", "correction"] {
                        ui.selectable_value(&mut app.admin.adjust_reason, reason.to_string(), reason);
                    }
                });
            ui.add_space(6.0);
            w::field_label(ui, "Notes");
            ui.add_sized([ui.available_width(), 32.0], TextEdit::singleline(&mut app.admin.adjust_notes));
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() { close = true; }
                if w::primary(ui, "Apply").clicked() { apply = true; }
            });
        });
    if close { app.admin.adjust_product_id = None; }
    if apply {
        let bid = business_id(app);
        let uid = app.user_id().unwrap_or_default();
        let delta = app.admin.adjust_delta.parse::<f64>().unwrap_or(0.0);
        let notes = app.admin.adjust_notes.trim();
        let notes = if notes.is_empty() { None } else { Some(notes) };
        let result = {
            let conn = app.db.conn();
            inventory::adjust_stock(&conn, &bid, &uid, &product_id, delta, &app.admin.adjust_reason, notes, app.is_owner())
        };
        match result {
            Ok(_) => {
                app.set_status("Stock adjusted", false);
                app.admin.adjust_product_id = None;
                load_products(app);
                load_movements(app);
                app.pos.refresh_needed = true;
            }
            Err(e) => app.show_error("Could not adjust stock", e),
        }
    }
}

fn two_fields(ui: &mut Ui, left_label: &str, left: &mut String, right_label: &str, right: &mut String) {
    ui.horizontal(|ui| {
        ui.vertical(|ui| {
            w::field_label(ui, left_label);
            ui.add_sized([186.0, 32.0], TextEdit::singleline(left));
        });
        ui.add_space(12.0);
        ui.vertical(|ui| {
            w::field_label(ui, right_label);
            ui.add_sized([186.0, 32.0], TextEdit::singleline(right));
        });
    });
    ui.add_space(8.0);
}

/* -------------------------------- customers ------------------------------ */

fn customers(app: &mut App, ui: &mut Ui) {
    if let Some(id) = app.admin.selected_customer_id.clone() {
        customer_detail(app, ui, &id);
        return;
    }
    w::page_header(ui, "Customers", "Your contacts, history and relationships");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_sized([240.0, 32.0], TextEdit::singleline(&mut app.admin.customer_query).hint_text("Search name, phone or email…"));
            if w::secondary(ui, "Search").clicked() {
                app.admin.customer_offset = 0;
                load_customers(app);
            }
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if w::primary(ui, "+  Add customer").clicked() {
                    app.admin.customer_form = Some(CustomerForm::default());
                }
            });
        });
        ui.add_space(10.0);
        ui.separator();
        let customers = app.admin.customers.clone();
        if customers.is_empty() {
            w::empty_state(ui, "No customers found", "Add customers to track their purchase history.");
        } else {
            table(ui, &["Name", "Phone", "Email", "City", ""], customers.iter().map(|c| {
                vec![c.name.clone(), c.phone.clone(), c.email.clone(), c.city.clone(), "Open".to_string()]
            }));
            ui.add_space(6.0);
            for customer in customers.iter().take(PAGE_SIZE as usize) {
                ui.horizontal(|ui| {
                    w::muted(ui, &customer.name);
                    if w::link(ui, "View details").clicked() {
                        app.admin.selected_customer_id = Some(customer.id.clone());
                        load_customer_detail(app, &customer.id);
                    }
                    if w::link(ui, "Edit").clicked() {
                        app.admin.customer_form = Some(CustomerForm {
                            id: Some(customer.id.clone()),
                            name: customer.name.clone(),
                            phone: customer.phone.clone(),
                            email: customer.email.clone(),
                            address: customer.address.clone(),
                            city: customer.city.clone(),
                            state: customer.state.clone(),
                            pincode: customer.pincode.clone(),
                            gstin: customer.gstin.clone(),
                            notes: customer.notes.clone().unwrap_or_default(),
                        });
                    }
                });
            }
        }
        if w::pagination(ui, &mut app.admin.customer_offset, PAGE_SIZE, app.admin.customer_total, "customers") {
            load_customers(app);
        }
    });
    if app.admin.customer_form.is_some() {
        customer_form_modal(app, ui.ctx());
    }
}

fn load_customer_detail(app: &mut App, id: &str) {
    let bid = business_id(app);
    let stats = {
        let conn = app.db.conn();
        repo::customer_stats(&conn, &bid, id)
    };
    let interactions = {
        let conn = app.db.conn();
        repo::list_interactions(&conn, &bid, id)
    };
    match stats {
        Ok(stats) => app.admin.customer_stats = Some(stats),
        Err(e) => app.show_error("Could not load customer stats", e),
    }
    match interactions {
        Ok(items) => app.admin.interactions = items,
        Err(e) => app.show_error("Could not load interactions", e),
    }
}

fn customer_detail(app: &mut App, ui: &mut Ui, id: &str) {
    let customer = app.admin.customers.iter().find(|c| c.id == id).cloned();
    let Some(customer) = customer else {
        w::empty_state(ui, "Customer not found", "Return to the list and try again.");
        return;
    };
    if w::secondary(ui, "←  All customers").clicked() {
        app.admin.selected_customer_id = None;
    }
    ui.add_space(12.0);
    ui.label(egui::RichText::new(&customer.name).size(21.0).color(INK).strong());
    w::muted(ui, format!("{} · {}", customer.phone, customer.email));
    ui.add_space(14.0);

    if let Some(stats) = &app.admin.customer_stats {
        let purchases = app.money(stats.total_purchases);
        let outstanding = app.money(stats.outstanding_balance);
        kpi_row(ui, &[
            ("Total purchases", purchases.as_str(), "Lifetime value"),
            ("Invoices", &format!("{}", stats.invoice_count), "Total invoices"),
            ("Outstanding", outstanding.as_str(), "Balance due"),
            ("Last invoice", stats.last_invoice_date.as_deref().unwrap_or("—"), "Most recent sale"),
        ]);
    }
    ui.add_space(18.0);

    w::flat_card(ui, |ui| {
        w::section_title(ui, "Interactions", Some("Calls, notes and follow-ups"));
        ui.add_space(8.0);
        if app.admin.interactions.is_empty() {
            w::empty_state(ui, "No interactions yet", "Record a note or call below.");
        } else {
            table(ui, &["Type", "Content", "When"], app.admin.interactions.iter().map(|(kind, content, date)| {
                vec![kind.clone(), content.clone(), date.clone()]
            }));
        }
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            ui.add_sized([ui.available_width() - 90.0, 32.0], TextEdit::singleline(&mut app.admin.interaction_text).hint_text("Add a note…"));
            if w::primary(ui, "Add").clicked() {
                let bid = business_id(app);
                let uid = app.user_id().unwrap_or_default();
                let note = app.admin.interaction_text.trim().to_string();
                if !note.is_empty() {
                    let result = {
                        let conn = app.db.conn();
                        repo::add_interaction(&conn, &bid, id, Some(&uid), "note", &note)
                    };
                    match result {
                        Ok(_) => {
                            app.admin.interaction_text.clear();
                            load_customer_detail(app, id);
                            app.set_status("Interaction added", false);
                        }
                        Err(e) => app.show_error("Could not add interaction", e),
                    }
                }
            }
        });
    });
}

fn customer_form_modal(app: &mut App, ctx: &Context) {
    let Some(mut form) = app.admin.customer_form.clone() else { return };
    let mut save = false;
    let mut cancel = false;
    egui::Window::new(if form.id.is_some() { "Edit customer" } else { "New customer" })
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(420.0);
            two_fields(ui, "Name", &mut form.name, "Phone", &mut form.phone);
            two_fields(ui, "Email", &mut form.email, "GSTIN", &mut form.gstin);
            two_fields(ui, "City", &mut form.city, "State", &mut form.state);
            two_fields(ui, "Pincode", &mut form.pincode, "Address", &mut form.address);
            w::field_label(ui, "Notes");
            ui.add_sized([ui.available_width(), 32.0], TextEdit::singleline(&mut form.notes));
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() { cancel = true; }
                if w::primary(ui, "Save customer").clicked() { save = true; }
            });
        });
    if cancel { app.admin.customer_form = None; }
    if save {
        let bid = business_id(app);
        let input = repo::CustomerInput {
            name: form.name.trim().to_string(),
            phone: optional(&form.phone),
            email: optional(&form.email),
            address: optional(&form.address),
            city: optional(&form.city),
            state: optional(&form.state),
            pincode: optional(&form.pincode),
            gstin: optional(&form.gstin),
            notes: optional(&form.notes),
        };
        let result = {
            let conn = app.db.conn();
            match &form.id {
                Some(id) => repo::update_customer(&conn, &bid, id, &input).map(|_| ()),
                None => repo::insert_customer(&conn, &bid, &input).map(|_| ()),
            }
        };
        match result {
            Ok(_) => {
                app.set_status("Customer saved", false);
                app.admin.customer_form = None;
                load_customers(app);
                app.pos.refresh_needed = true;
            }
            Err(e) => app.show_error("Could not save customer", e),
        }
    }
}

fn optional(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() { None } else { Some(trimmed.to_string()) }
}

/* -------------------------------- payments ------------------------------- */

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn payments_page(app: &mut App, ui: &mut Ui) {
    w::page_header(ui, "Payments", "Collections, confirmations and reconciliation");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_sized([220.0, 32.0], TextEdit::singleline(&mut app.admin.payment_query).hint_text("Search payments…"));
            egui::ComboBox::from_id_source("payment_status_filter")
                .selected_text(format!("Status: {}", app.admin.payment_status))
                .show_ui(ui, |ui| {
                    for option in ["all", "pending", "confirmed"] {
                        ui.selectable_value(&mut app.admin.payment_status, option.to_string(), option);
                    }
                });
            if w::secondary(ui, "Search").clicked() {
                app.admin.payment_offset = 0;
                load_payments(app);
            }
        });
        ui.add_space(10.0);
        ui.separator();
        let payments = app.admin.payments.clone();
        if payments.is_empty() {
            w::empty_state(ui, "No payments found", "Payments recorded at checkout appear here.");
        } else {
            table(ui, &["Invoice", "Customer", "Method", "Amount", "Status", "Date", ""], payments.iter().map(|p| {
                vec![p.invoice_number.clone().unwrap_or_else(|| "—".to_string()), p.customer_name.clone().unwrap_or_else(|| "—".to_string()), method_label(&p.method).to_string(), app.money(p.amount), p.status.clone(), p.created_at.clone(), if p.status == "pending" { "Confirm".to_string() } else { String::new() }]
            }));
            ui.add_space(6.0);
            for payment in payments.iter().take(PAGE_SIZE as usize) {
                if payment.status == "pending" {
                    ui.horizontal(|ui| {
                        w::muted(ui, payment.invoice_number.as_deref().unwrap_or("Payment"));
                        if w::link(ui, "Confirm payment").clicked() {
                            app.admin.confirm_payment_id = Some(payment.id.clone());
                            app.admin.confirm_reference.clear();
                        }
                    });
                }
            }
        }
        if w::pagination(ui, &mut app.admin.payment_offset, PAGE_SIZE, app.admin.payment_total, "payments") {
            load_payments(app);
        }
    });
    if app.admin.confirm_payment_id.is_some() {
        confirm_modal(app, ui.ctx());
    }
}

fn confirm_modal(app: &mut App, ctx: &Context) {
    let Some(payment_id) = app.admin.confirm_payment_id.clone() else { return };
    let mut close = false;
    let mut confirm = false;
    egui::Window::new("Confirm payment")
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(360.0);
            w::muted(ui, "Enter the bank reference (UTR) shown by your payment app.");
            ui.add_space(10.0);
            w::field_label(ui, "Reference");
            ui.add_sized([ui.available_width(), 32.0], TextEdit::singleline(&mut app.admin.confirm_reference).hint_text("Optional UTR / reference"));
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() { close = true; }
                if w::primary(ui, "Confirm").clicked() { confirm = true; }
            });
        });
    if close { app.admin.confirm_payment_id = None; }
    if confirm {
        let bid = business_id(app);
        let uid = app.user_id().unwrap_or_default();
        let reference = app.admin.confirm_reference.trim().to_string();
        let result = {
            let conn = app.db.conn();
            payments::confirm_payment(&conn, &bid, &payment_id, &uid, &reference)
        };
        match result {
            Ok(_) => {
                app.set_status("Payment confirmed", false);
                app.admin.confirm_payment_id = None;
                load_payments(app);
            }
            Err(e) => app.show_error("Could not confirm payment", e),
        }
    }
}

/* -------------------------------- analytics ------------------------------ */

fn analytics_page(app: &mut App, ui: &mut Ui) {
    w::page_header(ui, "Analytics & Reports", "Dive into sales, collections and customer performance");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            w::field_label(ui, "From date");
            ui.add_sized([130.0, 32.0], TextEdit::singleline(&mut app.admin.analytics_from).hint_text("YYYY-MM-DD"));
            ui.add_space(8.0);
            w::field_label(ui, "To date");
            ui.add_sized([130.0, 32.0], TextEdit::singleline(&mut app.admin.analytics_to).hint_text("YYYY-MM-DD"));
            ui.add_space(8.0);
            if w::primary(ui, "Apply range").clicked() { load_analytics_for_page(app); }
            if w::ghost(ui, "Clear").clicked() {
                app.admin.analytics_from.clear();
                app.admin.analytics_to.clear();
                load_analytics_for_page(app);
            }
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if w::secondary(ui, "Download CSV").clicked() { download_csv(app); }
            });
        });
    });
    ui.add_space(18.0);

    let data = app.admin.analytics.clone().unwrap_or_else(empty_analytics);
    let sales = app.money(data.month_sales);
    let collections = app.money(data.month_collections);
    let outstanding = app.money(data.outstanding);
    kpi_row(ui, &[
        ("Total sales", sales.as_str(), "In selected range"),
        ("Collections", collections.as_str(), "Cash received"),
        ("Outstanding", outstanding.as_str(), &format!("{} pending invoices", data.pending_invoices)),
        ("Customers", &format!("{}", data.total_customers), &format!("{} active", data.active_customers)),
    ]);
    ui.add_space(18.0);

    ui.horizontal(|ui| {
        let total = ui.available_width();
        ui.allocate_ui(Vec2::new((total - 18.0) * 0.7, ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Sales vs Collections", Some("Revenue billed against cash received"));
                ui.add_space(12.0);
                trend_chart(ui, &data.sales_trend);
                ui.add_space(8.0);
                chart_legend(ui);
            });
        });
        ui.add_space(18.0);
        ui.allocate_ui(Vec2::new(ui.available_width(), ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Payment Methods", Some("How your customers pay"));
                ui.add_space(12.0);
                method_chart(ui, &data.methods);
            });
        });
    });
    ui.add_space(18.0);

    ui.horizontal(|ui| {
        let total = ui.available_width();
        ui.allocate_ui(Vec2::new((total - 18.0) * 0.5, ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Top Products", Some("Highest revenue contributors"));
                ui.add_space(10.0);
                if data.top_products.is_empty() {
                    w::empty_state(ui, "No product data", "Sales appear here after the first invoice.");
                } else {
                    table(ui, &["Product", "Qty", "Revenue"], data.top_products.iter().map(|p| {
                        vec![p.name.clone(), format!("{}", p.quantity), app.money(p.revenue)]
                    }));
                }
            });
        });
        ui.add_space(18.0);
        ui.allocate_ui(Vec2::new(ui.available_width(), ui.available_height()), |ui| {
            w::flat_card(ui, |ui| {
                w::section_title(ui, "Top Customers", Some("Your most valuable relationships"));
                ui.add_space(10.0);
                if data.top_customers.is_empty() {
                    w::empty_state(ui, "No customer data", "Data appears here after your first sale.");
                } else {
                    table(ui, &["Customer", "Purchases", "Invoices"], data.top_customers.iter().map(|c| {
                        vec![c.name.clone(), app.money(c.purchases), format!("{}", c.count)]
                    }));
                }
            });
        });
    });
}

fn load_analytics_for_page(app: &mut App) {
    let from = optional(&app.admin.analytics_from);
    let to = optional(&app.admin.analytics_to);
    load_analytics(app, Some((from, to)));
}

fn download_csv(app: &mut App) {
    let bid = business_id(app);
    let from = optional(&app.admin.analytics_from);
    let to = optional(&app.admin.analytics_to);
    let result = {
        let conn = app.db.conn();
        reports::sales_csv(&conn, &bid, from.as_deref(), to.as_deref())
    };
    match result {
        Ok(csv) => {
            if let Some(path) = save_export("billflow-sales-report.csv", csv.as_bytes()) {
                app.set_status(format!("CSV saved to {}", path.display()), false);
            }
        }
        Err(e) => app.show_error("Could not create CSV", e),
    }
}

/* --------------------------------- staff --------------------------------- */

fn staff(app: &mut App, ui: &mut Ui) {
    if !app.is_owner() {
        w::empty_state(ui, "Owner access required", "Only the business owner can manage staff.");
        return;
    }
    w::page_header(ui, "Staff", "Manage team access and roles");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            w::muted(ui, format!("{} team members", app.admin.staff.len()));
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if w::primary(ui, "+  Add staff").clicked() {
                    app.admin.staff_form = Some(StaffForm::default());
                }
            });
        });
        ui.add_space(10.0);
        ui.separator();
        let users = app.admin.staff.clone();
        table(ui, &["Name", "Email", "Role", "Status", ""], users.iter().map(|u| {
            vec![u.full_name.clone(), u.email.clone(), if auth::is_owner(u) { "Owner".to_string() } else { "Staff".to_string() }, if u.is_active { "Active".to_string() } else { "Inactive".to_string() }, if u.is_active { "Deactivate".to_string() } else { "Activate".to_string() }]
        }));
        ui.add_space(6.0);
        for user in users.iter().take(PAGE_SIZE as usize) {
            if !auth::is_owner(user) {
                ui.horizontal(|ui| {
                    w::muted(ui, &user.full_name);
                    let label = if user.is_active { "Deactivate" } else { "Activate" };
                    if w::link(ui, label).clicked() {
                        let result = {
                            let conn = app.db.conn();
                            auth::set_user_active(&conn, &user.id, !user.is_active)
                        };
                        match result {
                            Ok(_) => {
                                app.set_status("Staff status updated", false);
                                load_staff(app);
                            }
                            Err(e) => app.show_error("Could not update staff", e),
                        }
                    }
                });
            }
        }
    });
    if app.admin.staff_form.is_some() {
        staff_form_modal(app, ui.ctx());
    }
}

fn staff_form_modal(app: &mut App, ctx: &Context) {
    let Some(mut form) = app.admin.staff_form.clone() else { return };
    let mut save = false;
    let mut cancel = false;
    egui::Window::new("Add team member")
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(400.0);
            two_fields(ui, "Full name", &mut form.full_name, "Email", &mut form.email);
            two_fields(ui, "Phone", &mut form.phone, "Password", &mut form.password);
            ui.checkbox(&mut form.is_owner, "Owner access");
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() { cancel = true; }
                if w::primary(ui, "Create user").clicked() { save = true; }
            });
        });
    if cancel { app.admin.staff_form = None; }
    if save {
        let bid = business_id(app);
        let phone = optional(&form.phone);
        let role = if form.is_owner { Role::Owner } else { Role::Staff };
        let result = {
            let conn = app.db.conn();
            auth::create_user(&conn, &bid, &form.full_name, &form.email, phone.as_deref(), &form.password, role)
        };
        match result {
            Ok(_) => {
                app.set_status("Team member created", false);
                app.admin.staff_form = None;
                load_staff(app);
            }
            Err(e) => app.show_error("Could not create user", e),
        }
    }
}

/* -------------------------------- activity ------------------------------- */

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn activity(app: &mut App, ui: &mut Ui) {
    w::page_header(ui, "Activity log", "A record of everything that happened");
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            egui::ComboBox::from_id_source("activity_category")
                .selected_text(format!("Category: {}", app.admin.activity_category))
                .show_ui(ui, |ui| {
                    for option in ["all", "invoice", "payment", "stock", "product", "customer", "staff", "pos"] {
                        ui.selectable_value(&mut app.admin.activity_category, option.to_string(), option);
                    }
                });
            ui.add_sized([200.0, 32.0], TextEdit::singleline(&mut app.admin.activity_query).hint_text("Search activity…"));
            if w::secondary(ui, "Search").clicked() {
                app.admin.activity_offset = 0;
                load_activity(app);
            }
        });
        ui.add_space(10.0);
        ui.separator();
        let logs = app.admin.activities.clone();
        if logs.is_empty() {
            w::empty_state(ui, "No activity yet", "Actions across the app are logged here.");
        } else {
            table(ui, &["When", "User", "Action", "Category", "Details"], logs.iter().map(|log| {
                vec![log.created_at.clone(), log.user_name.clone(), log.action.clone(), log.category.clone(), log.details.clone().unwrap_or_else(|| "—".to_string())]
            }));
        }
        if w::pagination(ui, &mut app.admin.activity_offset, PAGE_SIZE, app.admin.activity_total, "activity") {
            load_activity(app);
        }
    });
}

/* -------------------------------- settings ------------------------------- */

fn settings(app: &mut App, ui: &mut Ui) {
    w::page_header(ui, "Settings", "Business profile, UPI and team access");
    w::flat_card(ui, |ui| {
        w::section_title(ui, "Business profile", Some("Shown on invoices and receipts"));
        ui.add_space(10.0);
        two_fields(ui, "Business name", &mut app.admin.business_form.name, "Legal name", &mut app.admin.business_form.legal_name);
        two_fields(ui, "Email", &mut app.admin.business_form.email, "Phone", &mut app.admin.business_form.phone);
        two_fields(ui, "Address", &mut app.admin.business_form.address, "City", &mut app.admin.business_form.city);
        two_fields(ui, "State", &mut app.admin.business_form.state, "Pincode", &mut app.admin.business_form.pincode);
        two_fields(ui, "GSTIN", &mut app.admin.business_form.gstin, "Currency", &mut app.admin.business_form.currency);
        two_fields(ui, "Invoice prefix", &mut app.admin.business_form.invoice_prefix, "Default GST %", &mut app.admin.business_form.default_gst_rate);
        ui.add_space(14.0);
        ui.separator();
        ui.add_space(10.0);
        w::section_title(ui, "UPI & invoicing", None);
        ui.add_space(8.0);
        two_fields(ui, "UPI ID", &mut app.admin.business_form.upi_id, "UPI name", &mut app.admin.business_form.upi_name);
        two_fields(ui, "Low stock threshold", &mut app.admin.business_form.low_stock_threshold, "Invoice footer", &mut app.admin.business_form.invoice_footer);
        ui.add_space(12.0);
        if w::primary(ui, "Save changes").clicked() { save_business(app); }
    });
    ui.add_space(18.0);
    w::flat_card(ui, |ui| {
        w::section_title(ui, "Data & backups", Some("Local SQLite database on this device"));
        ui.add_space(10.0);
        w::muted(ui, format!("Database: {}", billflow_shared::db::default_db_path().display()));
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            if w::secondary(ui, "Back up database").clicked() { backup_database(app); }
            if w::secondary(ui, "Restore from backup").clicked() { restore_database(app); }
        });
    });
}

fn save_business(app: &mut App) {
    let bid = business_id(app);
    let form = app.admin.business_form.clone();
    let input = repo::BusinessInput {
        name: form.name,
        legal_name: optional(&form.legal_name),
        email: form.email,
        phone: form.phone,
        address: form.address,
        city: form.city,
        state: form.state,
        pincode: form.pincode,
        gstin: form.gstin,
        upi_id: form.upi_id,
        upi_name: form.upi_name,
        currency: form.currency,
        invoice_prefix: form.invoice_prefix,
        invoice_footer: optional(&form.invoice_footer),
        default_gst_rate: form.default_gst_rate.parse().unwrap_or(0.0),
        low_stock_threshold: form.low_stock_threshold.parse().unwrap_or(0.0),
    };
    let result = {
        let conn = app.db.conn();
        repo::update_business(&conn, &bid, &input)
    };
    match result {
        Ok(business) => {
            app.business = Some(business);
            app.set_status("Business settings saved", false);
        }
        Err(e) => app.show_error("Could not save settings", e),
    }
}

fn backup_database(app: &mut App) {
    let dir = app_data_dir().join("exports");
    if std::fs::create_dir_all(&dir).is_err() {
        app.set_status("Could not create exports folder", true);
        return;
    }
    let stamp = chrono::Local::now().format("%Y%m%d-%H%M%S");
    let target = dir.join(format!("billflow-backup-{}.sqlite3", stamp));
    let result = app.db.backup(&target);
    match result {
        Ok(_) => app.set_status(format!("Backup saved to {}", target.display()), false),
        Err(e) => app.show_error("Backup failed", e),
    }
}

fn restore_database(app: &mut App) {
    let dir = app_data_dir().join("exports");
    let Ok(entries) = std::fs::read_dir(&dir) else {
        app.set_status("No backups found", true);
        return;
    };
    let mut backups: Vec<_> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.to_string_lossy().ends_with(".sqlite3"))
        .collect();
    backups.sort();
    let Some(latest) = backups.pop() else {
        app.set_status("No backups found", true);
        return;
    };
    let result = app.db.restore(&latest);
    match result {
        Ok(_) => {
            app.set_status(format!("Restored from {}", latest.display()), false);
            app.admin.refresh_needed = true;
            app.pos.refresh_needed = true;
        }
        Err(e) => app.show_error("Restore failed", e),
    }
}

/* -------------------------------- helpers -------------------------------- */

fn truncate(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        text.to_string()
    } else {
        let prefix: String = text.chars().take(max.saturating_sub(1)).collect();
        format!("{}…", prefix)
    }
}
