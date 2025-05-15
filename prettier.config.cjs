/** @type {import('prettier').Config} */

const config = {
  bracketSpacing: true,
  // https://github.com/prettier/prettier/issues/15388#issuecomment-1717746872
  plugins: [require.resolve("@prettier/plugin-xml")],
  printWidth: 120,
  proseWrap: "always",
  semi: false,
  tabWidth: 2,
  trailingComma: "all",
  xmlWhitespaceSensitivity: "preserve",
}

module.exports = config
