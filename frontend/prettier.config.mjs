/** @type {import("prettier").Config} */
export default {
  endOfLine: "lf",
  plugins: ["prettier-plugin-tailwindcss"],
  printWidth: 100,
  semi: false,
  singleQuote: false,
  tabWidth: 2,
  tailwindStylesheet: "./src/index.css",
  trailingComma: "all",
}
