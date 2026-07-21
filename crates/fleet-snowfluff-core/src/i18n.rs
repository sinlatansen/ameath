//! Locale dictionary embedding (task 11.2, design.md D-locale): the five
//! `locales/*.json` files at the repo root are the single source of
//! truth for every user-facing string (localization spec). Embedding
//! them here rather than in the Tauri shell lets both the webview
//! command (11.2) and native tray/menu label resolution (11.3) share
//! one lookup without duplicating the JSON.

use std::collections::HashMap;

use crate::locale::UiLanguage;

const ZH_HANT_JSON: &str = include_str!("../../../locales/zh-Hant.json");
const ZH_HANS_JSON: &str = include_str!("../../../locales/zh-Hans.json");
const EN_JSON: &str = include_str!("../../../locales/en.json");
const JA_JSON: &str = include_str!("../../../locales/ja.json");
const KO_JSON: &str = include_str!("../../../locales/ko.json");

/// The raw JSON text for `lang`'s dictionary, exactly as authored --
/// this is what the webview command hands to the frontend for it to
/// `JSON.parse` itself (localization spec: JSON is the single source of
/// truth for both Rust and the webview).
pub fn dictionary_json(lang: UiLanguage) -> &'static str {
    match lang {
        UiLanguage::ZhHant => ZH_HANT_JSON,
        UiLanguage::ZhHans => ZH_HANS_JSON,
        UiLanguage::En => EN_JSON,
        UiLanguage::Ja => JA_JSON,
        UiLanguage::Ko => KO_JSON,
    }
}

/// Parses `lang`'s dictionary for native-side lookups (task 11.3's tray
/// and quick-menu labels). Panics on malformed JSON -- the five
/// `locales/*.json` files are authored content checked into this repo,
/// not user input, so a parse failure here is a build-time bug, not a
/// runtime condition to recover from.
pub fn dictionary(lang: UiLanguage) -> HashMap<String, String> {
    serde_json::from_str(dictionary_json(lang))
        .unwrap_or_else(|err| panic!("locales/*.json for {lang:?} is malformed: {err}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_locale_parses_and_shares_the_same_key_set() {
        let languages = [
            UiLanguage::ZhHant,
            UiLanguage::ZhHans,
            UiLanguage::En,
            UiLanguage::Ja,
            UiLanguage::Ko,
        ];
        let reference: std::collections::BTreeSet<_> =
            dictionary(UiLanguage::En).into_keys().collect();
        for lang in languages {
            let keys: std::collections::BTreeSet<_> = dictionary(lang).into_keys().collect();
            assert_eq!(keys, reference, "{lang:?} dictionary key set diverges from en");
        }
    }
}
