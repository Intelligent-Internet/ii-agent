use chrono::{SecondsFormat, Utc};

pub fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

pub fn generate_message_id() -> String {
    format!("cowork-msg-{}", Utc::now().timestamp_millis())
}
