import english from "./en";
import marathi from "./mr";

const translations = { en: english, mr: marathi };

export function translate(language, key) {
  return translations[language]?.[key] || english[key] || key;
}
