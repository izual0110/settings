"use strict";

const SCRIPT_URL = "https://raw.githubusercontent.com/izual0110/settings/master/generate-devcontainer.sh";
// Update pinned releases here and in generate-devcontainer.sh together.
const DISTRIBUTIONS = {
  ubuntu: {
    name: "Ubuntu",
    image: "ubuntu",
    defaultVersion: "lts",
    versions: [
      { value: "lts", label: "26.04 LTS", note: "recommended", tag: "26.04" },
      { value: "24.04", label: "24.04 LTS", tag: "24.04" },
      { value: "22.04", label: "22.04 LTS", tag: "22.04" },
      { value: "current", label: "Latest release", note: "26.04", tag: "26.04" },
      { value: "latest", label: "latest", note: "floating tag", tag: "latest" },
    ],
  },
  fedora: {
    name: "Fedora",
    image: "quay.io/fedora/fedora",
    defaultVersion: "current",
    versions: [
      { value: "current", label: "Latest release", note: "44", tag: "44" },
      { value: "latest", label: "latest", note: "floating tag", tag: "latest" },
    ],
  },
  alpine: {
    name: "Alpine",
    image: "alpine",
    defaultVersion: "current",
    versions: [
      { value: "current", label: "Latest release", note: "3.24", tag: "3.24" },
      { value: "latest", label: "latest", note: "floating tag", tag: "latest" },
    ],
  },
};

const FLAG_LABELS = {
  java: "Java 25 LTS", "java-lts": "Java 25 LTS", "java-latest": "Java 27 (latest)",
  maven: "Maven", gradle: "Gradle",
  clojure: "Clojure CLI 1.12.6.1673", php: "PHP", go: "Go", "build-tools": "Build tools",
  jq: "jq", unzip: "unzip", mariadb: "MariaDB client",
  claude: "Claude Code", codex: "Codex",
  force: "overwrite files",
};

function buildCommand(os, version, flags) {
  if (!Object.hasOwnProperty.call(DISTRIBUTIONS, os) ||
      !DISTRIBUTIONS[os].versions.some((release) => release.value === version) ||
      flags.some((flag) => !Object.hasOwnProperty.call(FLAG_LABELS, flag))) {
    throw new Error("Unknown generator option");
  }
  if (flags.filter((flag) => ["java", "java-lts", "java-latest"].includes(flag)).length > 1) {
    throw new Error("The --java, --java-lts, and --java-latest options are mutually exclusive");
  }
  const args = ["--os", os, "--version", version, ...flags.map((flag) => `--${flag}`)];
  return `curl -fsSL '${SCRIPT_URL}' | bash -s -- ${args.join(" ")}`;
}

const form = document.getElementById("configuration");
const versions = document.getElementById("versions");
const command = document.getElementById("command");
const copyButton = document.getElementById("copy");
const copyStatus = document.getElementById("copy-status");

function selectedOS() {
  return form.querySelector('input[name="os"]:checked').value;
}

function renderVersions() {
  const distribution = DISTRIBUTIONS[selectedOS()];
  versions.replaceChildren();
  for (const release of distribution.versions) {
    const label = document.createElement("label");
    label.className = "choice version-choice";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "version";
    input.value = release.value;
    input.checked = release.value === distribution.defaultVersion;
    const text = document.createElement("span");
    text.textContent = release.label;
    if (release.note) {
      const note = document.createElement("small");
      note.textContent = release.note;
      text.append(note);
    }
    label.append(input, text);
    versions.append(label);
  }
}

function updateCommand() {
  const os = selectedOS();
  const version = form.querySelector('input[name="version"]:checked').value;
  const javaEnabled = document.getElementById("java").checked || document.getElementById("clojure").checked;
  const javaVersions = document.getElementById("java-versions");
  javaVersions.hidden = !javaEnabled;
  javaVersions.disabled = !javaEnabled;
  const javaTools = document.getElementById("java-tools");
  javaTools.hidden = !javaEnabled;
  javaTools.disabled = !javaEnabled;
  // form.elements also includes the --force checkbox outside the form.
  const flags = Array.from(form.elements)
    .filter((input) => input.checked && !input.matches(":disabled") && input.dataset.flag && input.dataset.flag !== "java")
    .map((input) => input.dataset.flag);
  if (javaEnabled) {
    flags.unshift(form.querySelector('input[name="java-version"]:checked').value);
  }
  const distribution = DISTRIBUTIONS[os];
  const release = distribution.versions.find((candidate) => candidate.value === version);
  command.value = buildCommand(os, version, flags);
  document.getElementById("image").textContent = `${distribution.image}:${release.tag}`;
  document.getElementById("summary").textContent = [distribution.name, ...flags.map((flag) => FLAG_LABELS[flag])].join(" · ");

  copyStatus.textContent = "";
}

form.addEventListener("submit", (event) => event.preventDefault());
form.addEventListener("change", (event) => {
  if (event.target.name === "os") renderVersions();
  updateCommand();
});
// The external checkbox's events do not bubble through the form.
document.getElementById("force").addEventListener("change", updateCommand);
document.getElementById("reset").addEventListener("click", () => {
  form.reset();
  renderVersions();
  updateCommand();
});

copyButton.addEventListener("click", async () => {
  const value = command.value;
  try {
    await navigator.clipboard.writeText(value);
    copyStatus.textContent = command.value === value ? "Command copied. Run it in your project folder." : "Previous selection copied. Copy the new command.";
  } catch {
    command.focus();
    command.select();
    copyStatus.textContent = "Automatic copying is unavailable. The command is selected — press Ctrl+C or ⌘C.";
  }
});

renderVersions();
updateCommand();
copyButton.disabled = false;
