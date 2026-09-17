module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "scope-enum": [
      2,
      "always",
      [
        "backend",
        "frontend",
        "scoring",
        "scanner",
        "triage",
        "admin",
        "docs",
        "ci",
        "release",
      ],
    ],
  },
};
