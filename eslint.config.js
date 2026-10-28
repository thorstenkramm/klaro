import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    files: ["src/klaro/static/klaro/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        document: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "no-var": "error",
      "prefer-const": "error",
      eqeqeq: "error",
    },
  },
];
