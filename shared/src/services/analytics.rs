//! Dashboard analytics, computed exclusively from persisted SQLite records.

use chrono::{Datelike, Duration, NaiveDate, Utc};
use rusqlite::{params_from_iter, types::Value, Connection};

use crate::error::Result;
use crate::models::{Invoice, Payment};
use crate::repo;

#[derive(Clone, Debug, PartialEq)]
pub struct TrendPoint {
    pub period: String,
    pub sales: f64,
    pub collections: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MethodRow {
    pub method: String,
    pub amount: f64,
    pub count: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TopProduct {
    pub name: String,
    pub quantity: f64,
    pub revenue: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TopCustomer {
    pub name: String,
    pub purchases: f64,
    pub count: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Analytics {
    pub today_sales: f64,
    pub today_transactions: i64,
    pub month_sales: f64,
    pub month_collections: f64,
    pub year_sales: f64,
    pub outstanding: f64,
    pub pending_invoices: i64,
    pub low_stock: i64,
    pub total_customers: i64,
    pub active_customers: i64,
    pub growth_percent: f64,
    pub sales_trend: Vec<TrendPoint>,
    pub methods: Vec<MethodRow>,
    pub top_products: Vec<TopProduct>,
    pub top_customers: Vec<TopCustomer>,
    pub recent_invoices: Vec<Invoice>,
    pub recent_payments: Vec<Payment>,
}

fn ymd(date: NaiveDate) -> String {
    date.format("%Y-%m-%d").to_string()
}

fn month_bounds(date: NaiveDate) -> (NaiveDate, NaiveDate) {
    let start = date.with_day(1).unwrap_or(date);
    let next_year = date.year() + if date.month() == 12 { 1 } else { 0 };
    let next_month = if date.month() == 12 { 1 } else { date.month() + 1 };
    let next = NaiveDate::from_ymd_opt(next_year, next_month, 1).unwrap_or(start);
    (start, next.pred_opt().unwrap_or(start))
}

fn previous_month(date: NaiveDate) -> NaiveDate {
    let (start, _) = month_bounds(date);
    let last_day_before = start.pred_opt().unwrap_or(start);
    last_day_before.with_day(1).unwrap_or(last_day_before)
}

fn f64_value(conn: &Connection, sql: &str, values: &[Value]) -> Result<f64> {
    Ok(conn
        .query_row(sql, params_from_iter(values.iter()), |row| {
            row.get::<_, Option<f64>>(0)
        })?
        .unwrap_or(0.0))
}

fn i64_value(conn: &Connection, sql: &str, values: &[Value]) -> Result<i64> {
    Ok(conn
        .query_row(sql, params_from_iter(values.iter()), |row| {
            row.get::<_, Option<i64>>(0)
        })?
        .unwrap_or(0))
}

/// Sum of non-cancelled invoice totals in an inclusive date range.
fn sales_sum(conn: &Connection, business_id: &str, from: Option<&str>, to: Option<&str>) -> Result<f64> {
    let mut values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut sql = String::from(
        "SELECT COALESCE(SUM(total_amount),0) FROM invoices WHERE business_id=?1 AND status!='cancelled'",
    );
    if let Some(f) = from {
        values.push(Value::Text(f.to_string()));
        sql.push_str(&format!(" AND issue_date>=?{}", values.len()));
    }
    if let Some(t) = to {
        values.push(Value::Text(t.to_string()));
        sql.push_str(&format!(" AND issue_date<=?{}", values.len()));
    }
    f64_value(conn, &sql, &values)
}

fn invoice_count(conn: &Connection, business_id: &str, from: Option<&str>, to: Option<&str>) -> Result<i64> {
    let mut values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut sql = String::from(
        "SELECT COUNT(*) FROM invoices WHERE business_id=?1 AND status!='cancelled'",
    );
    if let Some(f) = from {
        values.push(Value::Text(f.to_string()));
        sql.push_str(&format!(" AND issue_date>=?{}", values.len()));
    }
    if let Some(t) = to {
        values.push(Value::Text(t.to_string()));
        sql.push_str(&format!(" AND issue_date<=?{}", values.len()));
    }
    i64_value(conn, &sql, &values)
}

/// Sum of confirmed payments, using their payment date (or creation date).
fn collections_sum(conn: &Connection, business_id: &str, from: Option<&str>, to: Option<&str>) -> Result<f64> {
    let mut values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut sql = String::from(
        "SELECT COALESCE(SUM(amount),0) FROM payments WHERE business_id=?1 AND status='confirmed'",
    );
    let date_expr = "COALESCE(payment_date, substr(created_at,1,10))";
    if let Some(f) = from {
        values.push(Value::Text(f.to_string()));
        sql.push_str(&format!(" AND {date_expr}>=?{}", values.len()));
    }
    if let Some(t) = to {
        values.push(Value::Text(t.to_string()));
        sql.push_str(&format!(" AND {date_expr}<=?{}", values.len()));
    }
    f64_value(conn, &sql, &values)
}

fn date_filter_sql(values: &mut Vec<Value>, from: Option<&str>, to: Option<&str>, column: &str) -> String {
    let mut out = String::new();
    if let Some(f) = from {
        values.push(Value::Text(f.to_string()));
        out.push_str(&format!(" AND {column}>=?{}", values.len()));
    }
    if let Some(t) = to {
        values.push(Value::Text(t.to_string()));
        out.push_str(&format!(" AND {column}<=?{}", values.len()));
    }
    out
}

/// Load every dashboard metric for a business.
pub fn load(conn: &Connection, business_id: &str, from: Option<&str>, to: Option<&str>) -> Result<Analytics> {
    let today = Utc::now().date_naive();
    let today_str = ymd(today);
    let (month_start, month_end) = month_bounds(today);
    let (year_start, year_end) = (
        NaiveDate::from_ymd_opt(today.year(), 1, 1).unwrap_or(today),
        NaiveDate::from_ymd_opt(today.year(), 12, 31).unwrap_or(today),
    );
    let yesterday = month_start.pred_opt().unwrap_or(month_start);
    let (prev_start, prev_end) = month_bounds(yesterday);

    // Snapshot cards are independent of the selected report range.
    let today_sales = sales_sum(conn, business_id, Some(&today_str), Some(&today_str))?;
    let today_transactions = invoice_count(conn, business_id, Some(&today_str), Some(&today_str))?;
    let month_sales = sales_sum(conn, business_id, Some(&ymd(month_start)), Some(&ymd(month_end)))?;
    let month_collections =
        collections_sum(conn, business_id, Some(&ymd(month_start)), Some(&ymd(month_end)))?;
    let year_sales = sales_sum(conn, business_id, Some(&ymd(year_start)), Some(&ymd(year_end)))?;
    let prev_month_sales = sales_sum(conn, business_id, Some(&ymd(prev_start)), Some(&ymd(prev_end)))?;
    let growth_percent = if prev_month_sales > 0.0 {
        ((month_sales - prev_month_sales) / prev_month_sales) * 100.0
    } else if month_sales > 0.0 {
        100.0
    } else {
        0.0
    };

    // Outstanding balances.
    let (outstanding, pending_invoices) = conn.query_row(
        "SELECT COALESCE(SUM(balance_amount),0), COUNT(*) FROM invoices \
         WHERE business_id=?1 AND status IN ('unpaid','partially_paid')",
        [business_id],
        |row| Ok((row.get::<_, f64>(0)?, row.get::<_, i64>(1)?)),
    )?;

    // Customer and stock KPIs.
    let total_customers: i64 = conn.query_row(
        "SELECT COUNT(*) FROM customers WHERE business_id=?1 AND is_active=1",
        [business_id],
        |row| row.get(0),
    )?;
    let cutoff = ymd(today - Duration::days(90));
    let active_customers: i64 = conn.query_row(
        "SELECT COUNT(DISTINCT customer_id) FROM invoices WHERE business_id=?1 AND issue_date>=?2",
        [business_id, cutoff.as_str()],
        |row| row.get(0),
    )?;
    let low_stock: i64 = conn.query_row(
        "SELECT COUNT(*) FROM products WHERE business_id=?1 AND is_active=1 \
         AND track_inventory=1 AND stock<=low_stock_threshold",
        [business_id],
        |row| row.get(0),
    )?;

    // 12-month sales/collections trend ending at the selected month.
    let anchor = match from.and_then(|s| NaiveDate::parse_from_str(s, "%Y-%m-%d").ok()) {
        Some(date) => date,
        None => today,
    };
    let mut cursor = anchor.with_day(1).unwrap_or(anchor);
    let mut reversed_trend = Vec::new();
    for _ in 0..12 {
        let (start, end) = month_bounds(cursor);
        reversed_trend.push(TrendPoint {
            period: cursor.format("%b %Y").to_string(),
            sales: sales_sum(conn, business_id, Some(&ymd(start)), Some(&ymd(end)))?,
            collections: collections_sum(conn, business_id, Some(&ymd(start)), Some(&ymd(end)))?,
        });
        cursor = previous_month(start);
    }
    reversed_trend.reverse();

    // Payment method breakdown (confirmed payments only).
    let mut method_values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut method_sql = String::from(
        "SELECT method, COALESCE(SUM(amount),0), COUNT(*) FROM payments \
         WHERE business_id=?1 AND status='confirmed'",
    );
    method_sql.push_str(&date_filter_sql(
        &mut method_values,
        from,
        to,
        "COALESCE(payment_date, substr(created_at,1,10))",
    ));
    method_sql.push_str(" GROUP BY method ORDER BY SUM(amount) DESC");
    let mut stmt = conn.prepare(&method_sql)?;
    let rows = stmt.query_map(params_from_iter(method_values.iter()), |row| {
        Ok(MethodRow {
            method: crate::util::rs(row, "method")?,
            amount: row.get(1)?,
            count: row.get(2)?,
        })
    })?;
    let mut methods = Vec::new();
    for row in rows {
        methods.push(row?);
    }

    // Top products by line revenue.
    let mut product_values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut product_sql = String::from(
        "SELECT COALESCE(p.name, ii.description) AS name, COALESCE(SUM(ii.quantity),0), \
         COALESCE(SUM(ii.line_total),0) FROM invoice_items ii \
         JOIN invoices i ON i.id=ii.invoice_id \
         LEFT JOIN products p ON p.id=ii.product_id \
         WHERE i.business_id=?1 AND i.status!='cancelled'",
    );
    product_sql.push_str(&date_filter_sql(&mut product_values, from, to, "i.issue_date"));
    product_sql.push_str(
        " GROUP BY COALESCE(p.id, ii.product_id, ii.description) \
         ORDER BY SUM(ii.line_total) DESC LIMIT 5",
    );
    let mut stmt = conn.prepare(&product_sql)?;
    let rows = stmt.query_map(params_from_iter(product_values.iter()), |row| {
        Ok(TopProduct {
            name: row.get(0)?,
            quantity: row.get(1)?,
            revenue: row.get(2)?,
        })
    })?;
    let mut top_products = Vec::new();
    for row in rows {
        top_products.push(row?);
    }

    // Most valuable customers.
    let mut customer_values: Vec<Value> = vec![Value::Text(business_id.to_string())];
    let mut customer_sql = String::from(
        "SELECT c.name, COALESCE(SUM(i.total_amount),0), COUNT(i.id) \
         FROM customers c JOIN invoices i ON i.customer_id=c.id \
         WHERE i.business_id=?1 AND i.status!='cancelled'",
    );
    customer_sql.push_str(&date_filter_sql(&mut customer_values, from, to, "i.issue_date"));
    customer_sql.push_str(
        " GROUP BY c.id, c.name ORDER BY SUM(i.total_amount) DESC LIMIT 5",
    );
    let mut stmt = conn.prepare(&customer_sql)?;
    let rows = stmt.query_map(params_from_iter(customer_values.iter()), |row| {
        Ok(TopCustomer {
            name: row.get(0)?,
            purchases: row.get(1)?,
            count: row.get(2)?,
        })
    })?;
    let mut top_customers = Vec::new();
    for row in rows {
        top_customers.push(row?);
    }

    let (recent_invoices, _) = repo::list_invoices(conn, business_id, "", "", 5, 0)?;
    let (recent_payments, _) = repo::list_payments(conn, business_id, "", "", 5, 0)?;

    Ok(Analytics {
        today_sales,
        today_transactions,
        month_sales,
        month_collections,
        year_sales,
        outstanding,
        pending_invoices,
        low_stock,
        total_customers,
        active_customers,
        growth_percent,
        sales_trend: reversed_trend,
        methods,
        top_products,
        top_customers,
        recent_invoices,
        recent_payments,
    })
}
