// npx eslint@<pin> で実行するため、node_modules に依存する import は書かない。
// ルートの .js は QML JS ライブラリと node:test の両方で動く script。
// トップレベルの関数と変数が QML から見える API なので、未使用検査は local に限る。
export default [
  {
    files: ["*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        // typeof ガード付きの dual-env export（QML では未定義、node では CommonJS）
        module: "readonly",
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": ["error", { vars: "local", args: "none" }],
      "no-redeclare": "error",
      "no-dupe-keys": "error",
      "no-dupe-args": "error",
      "no-duplicate-case": "error",
      "no-unreachable": "error",
      "no-fallthrough": "error",
      "no-cond-assign": "error",
      "no-constant-condition": "error",
      "no-self-assign": "error",
      "no-self-compare": "error",
      "no-unsafe-negation": "error",
      "no-sparse-arrays": "error",
      "no-func-assign": "error",
      "no-global-assign": "error",
      "no-shadow-restricted-names": "error",
      "use-isnan": "error",
      "valid-typeof": "error",
      "eqeqeq": ["error", "smart"],
    },
  },
  {
    files: ["tests/**/*.cjs"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "commonjs",
      globals: {
        require: "readonly",
        module: "writable",
        exports: "writable",
        process: "readonly",
        console: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
        Buffer: "readonly",
        structuredClone: "readonly",
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": ["error", { args: "none" }],
      "no-redeclare": "error",
      "no-dupe-keys": "error",
      "no-unreachable": "error",
      "use-isnan": "error",
      "valid-typeof": "error",
      "eqeqeq": ["error", "smart"],
    },
  },
];
