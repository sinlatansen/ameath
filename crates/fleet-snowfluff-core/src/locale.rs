//! UI language detection and resolution (design.md D6). The resolution
//! chain itself is a pure function over an optional locale string so it's
//! testable without touching the OS; [`detect_ui_language`] is a thin
//! wrapper that feeds in the real system locale via `sys-locale`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum UiLanguage {
    #[default]
    ZhHant,
    ZhHans,
    En,
    Ja,
    Ko,
}

/// Resolves a system locale string (e.g. `"zh-TW"`, `"en_US.UTF-8"`,
/// `"ja-JP"`) to a supported UI language: zh-TW/HK/MO -> zh-Hant,
/// zh-CN/SG -> zh-Hans, en/ja/ko match by language prefix, anything else
/// (including no locale at all) falls back to zh-Hant.
pub fn resolve_ui_language(system_locale: Option<&str>) -> UiLanguage {
    let Some(locale) = system_locale else {
        return UiLanguage::ZhHant;
    };
    let normalized = locale.to_lowercase().replace('_', "-");

    if let Some(rest) = normalized.strip_prefix("zh") {
        if rest.contains("tw")
            || rest.contains("hk")
            || rest.contains("mo")
            || rest.contains("hant")
        {
            return UiLanguage::ZhHant;
        }
        if rest.contains("cn") || rest.contains("sg") || rest.contains("hans") {
            return UiLanguage::ZhHans;
        }
        return UiLanguage::ZhHant;
    }

    match normalized.split(['-', '.']).next().unwrap_or("") {
        "en" => UiLanguage::En,
        "ja" => UiLanguage::Ja,
        "ko" => UiLanguage::Ko,
        _ => UiLanguage::ZhHant,
    }
}

/// Detects the UI language from the real system locale.
pub fn detect_ui_language() -> UiLanguage {
    resolve_ui_language(sys_locale::get_locale().as_deref())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn taiwan_hongkong_macau_map_to_traditional() {
        assert_eq!(resolve_ui_language(Some("zh-TW")), UiLanguage::ZhHant);
        assert_eq!(resolve_ui_language(Some("zh-HK")), UiLanguage::ZhHant);
        assert_eq!(resolve_ui_language(Some("zh-MO")), UiLanguage::ZhHant);
    }

    #[test]
    fn mainland_singapore_map_to_simplified() {
        assert_eq!(resolve_ui_language(Some("zh-CN")), UiLanguage::ZhHans);
        assert_eq!(resolve_ui_language(Some("zh-SG")), UiLanguage::ZhHans);
    }

    #[test]
    fn en_ja_ko_match_by_prefix() {
        assert_eq!(resolve_ui_language(Some("en-US")), UiLanguage::En);
        assert_eq!(resolve_ui_language(Some("ja-JP")), UiLanguage::Ja);
        assert_eq!(resolve_ui_language(Some("ko-KR")), UiLanguage::Ko);
    }

    #[test]
    fn linux_style_locale_strings_are_normalized() {
        assert_eq!(resolve_ui_language(Some("en_US.UTF-8")), UiLanguage::En);
    }

    #[test]
    fn unmapped_locale_falls_back_to_traditional_chinese() {
        assert_eq!(resolve_ui_language(Some("fr-FR")), UiLanguage::ZhHant);
    }

    #[test]
    fn no_locale_falls_back_to_traditional_chinese() {
        assert_eq!(resolve_ui_language(None), UiLanguage::ZhHant);
    }

    #[test]
    fn bare_zh_without_region_falls_back_to_traditional() {
        assert_eq!(resolve_ui_language(Some("zh")), UiLanguage::ZhHant);
    }
}
