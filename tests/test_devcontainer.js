"use strict";

// Run with `node --test tests/test_devcontainer.js`; no third-party modules required.
// Optionally set DEVCONTAINER_JSDOM to a temporary jsdom module's absolute path
// to run the same assertions against its native DOM as well as the VM stubs.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "devcontainer.js"), "utf8");
const scriptURL = "https://raw.githubusercontent.com/izual0110/settings/master/generate-devcontainer.sh";
const expectedCommand = (args) => `curl -fsSL '${scriptURL}' | bash -s -- ${args}`;

class StubEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.bubbles = Boolean(options.bubbles);
  }

  preventDefault() {}
}

class StubElement {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName;
    this.attributes = attributes;
    this.id = attributes.id || "";
    this.name = attributes.name || "";
    this.type = attributes.type || "";
    this.value = attributes.value || "";
    this.dataset = Object.hasOwn(attributes, "data-flag") ? { flag: attributes["data-flag"] } : {};
    this.defaultChecked = Object.hasOwn(attributes, "checked");
    this.checked = this.defaultChecked;
    this.disabled = Object.hasOwn(attributes, "disabled");
    this.hidden = Object.hasOwn(attributes, "hidden");
    this.textContent = "";
    this.children = [];
    this.listeners = new Map();
    this.parentElement = null;
  }

  append(...children) {
    for (const child of children) {
      child.parentElement = this;
      this.children.push(child);
    }
  }

  replaceChildren(...children) {
    for (const child of this.children) child.parentElement = null;
    this.children = [];
    this.append(...children);
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  querySelector(selector) {
    const match = /^input\[name="([^"]+)"\]:checked$/.exec(selector);
    assert.ok(match, `Unsupported stub selector: ${selector}`);
    return this.descendants().find((element) =>
      element.tagName === "input" && element.name === match[1] && element.checked,
    ) || null;
  }

  matches(selector) {
    assert.equal(selector, ":disabled");
    if (this.disabled) return true;
    // The page has no controls in legends (which have a fieldset exception).
    for (let parent = this.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "fieldset" && parent.disabled) return true;
    }
    return false;
  }

  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    for (const callback of this.listeners.get(event.type) || []) callback(event);
    if (event.bubbles && this.parentElement) this.parentElement.dispatchEvent(event);
  }
}

function stubDocument() {
  const document = new StubElement("document");
  const stack = [document];
  const voidTags = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);
  // Read the real page's control attributes and ancestry, not a separate fixture.
  // Only element structure is needed; this is not a general HTML parser.
  for (const token of html.matchAll(/<\/?([a-z][a-z0-9-]*)\b([^>]*)>/gi)) {
    const tagName = token[1].toLowerCase();
    if (token[0].startsWith("</")) {
      assert.equal(stack.pop().tagName, tagName, "Unexpected page markup nesting");
      continue;
    }
    const attributes = {};
    for (const attribute of token[2].matchAll(/([^\s=\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attributes[attribute[1]] = attribute[2] ?? attribute[3] ?? attribute[4] ?? "";
    }
    const element = new StubElement(tagName, attributes);
    stack.at(-1).append(element);
    if (!voidTags.has(tagName)) stack.push(element);
  }
  assert.equal(stack.length, 1);
  document.getElementById = (id) => document.descendants().find((element) => element.id === id) || null;
  document.createElement = (tagName) => new StubElement(tagName);
  document.defaultView = { Event: StubEvent };
  const form = document.getElementById("configuration");
  Object.defineProperty(form, "elements", {
    get() {
      return document.descendants().filter((element) =>
        ["input", "textarea", "button", "fieldset"].includes(element.tagName) &&
        (form.descendants().includes(element) || element.attributes.form === form.id),
      );
    },
  });
  form.reset = () => {
    for (const element of form.elements) element.checked = element.defaultChecked;
  };
  return document;
}

function loadPage(backend) {
  let document;
  let buildCommand;
  if (backend === "jsdom") {
    const { JSDOM } = require(process.env.DEVCONTAINER_JSDOM);
    const dom = new JSDOM(html, { runScripts: "outside-only" });
    // Execute as a classic script: strict eval would hide top-level functions.
    vm.runInContext(source, dom.getInternalVMContext(), { filename: "devcontainer.js", timeout: 1000 });
    document = dom.window.document;
    buildCommand = dom.window.buildCommand;
  } else {
    document = stubDocument();
    const context = vm.createContext({ document });
    vm.runInContext(source, context, { filename: "devcontainer.js", timeout: 1000 });
    buildCommand = context.buildCommand;
  }
  const form = document.getElementById("configuration");
  const byId = (id) => {
    const element = document.getElementById(id);
    assert.ok(element, `Missing #${id}`);
    return element;
  };
  const flag = (name) => {
    const element = Array.from(form.elements).find((input) => input.dataset.flag === name);
    assert.ok(element, `Missing ${name} checkbox`);
    return element;
  };
  const change = (element) => element.dispatchEvent(new document.defaultView.Event("change", { bubbles: true }));
  return {
    byId, flag, buildCommand,
    check(name, checked) {
      const element = flag(name);
      element.checked = checked;
      change(element);
    },
    radio(name, value) {
      const inputs = Array.from(form.elements).filter((input) => input.name === name);
      const selected = inputs.find((input) => input.value === value);
      assert.ok(selected, `Missing ${name}=${value} radio`);
      for (const input of inputs) input.checked = input === selected;
      change(selected);
    },
    reset() {
      byId("reset").dispatchEvent(new document.defaultView.Event("click", { bubbles: true }));
    },
  };
}

function assertJavaControls(page, enabled) {
  for (const id of ["java-versions", "java-tools"]) {
    assert.equal(page.byId(id).hidden, !enabled, `${id} visibility`);
    assert.equal(page.byId(id).disabled, !enabled, `${id} disabled state`);
  }
  for (const name of ["maven", "gradle"]) {
    assert.equal(page.flag(name).disabled, false, `${name} uses inherited disabling`);
    assert.equal(page.flag(name).matches(":disabled"), !enabled, `${name} effective disabled state`);
  }
}

for (const backend of ["stub", ...(process.env.DEVCONTAINER_JSDOM ? ["jsdom"] : [])]) {
  test(`${backend}: initial defaults and Alpine commands/images`, () => {
    const page = loadPage(backend);
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts --java-lts"));
    assert.equal(page.byId("image").textContent, "ubuntu:26.04");
    assertJavaControls(page, true);
    assert.equal(page.flag("maven").checked, false);
    assert.equal(page.flag("gradle").checked, false);

    page.radio("os", "alpine");
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version current --java-lts"));
    assert.equal(page.byId("image").textContent, "alpine:3.24");
    page.radio("version", "latest");
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version latest --java-lts"));
    assert.equal(page.byId("image").textContent, "alpine:latest");
  });

  test(`${backend}: MariaDB client is optional and works for every distribution`, () => {
    const page = loadPage(backend);
    assert.equal(page.flag("mariadb").checked, false);
    page.check("java", false);
    for (const [os, version, label] of [
      ["ubuntu", "lts", "Ubuntu"],
      ["fedora", "current", "Fedora"],
      ["alpine", "current", "Alpine"],
    ]) {
      page.radio("os", os);
      page.check("mariadb", true);
      assert.equal(page.byId("command").value, expectedCommand(`--os ${os} --version ${version} --mariadb`));
      assert.equal(page.byId("summary").textContent, `${label} · MariaDB client`);
      page.check("mariadb", false);
      assert.equal(page.byId("command").value, expectedCommand(`--os ${os} --version ${version}`));
    }
    page.check("mariadb", true);
    page.reset();
    assert.equal(page.flag("mariadb").checked, false);
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts --java-lts"));
  });

  test(`${backend}: disabled Java tools retain checks but cannot leak flags`, () => {
    const page = loadPage(backend);
    page.radio("os", "alpine");
    page.radio("java-version", "java-latest");
    page.check("maven", true);
    page.check("gradle", true);
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version current --java-latest --maven --gradle"));

    page.check("java", false);
    assert.equal(page.flag("clojure").checked, false);
    assertJavaControls(page, false);
    assert.equal(page.flag("maven").checked, true);
    assert.equal(page.flag("gradle").checked, true);
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version current"));
    assert.equal(page.byId("summary").textContent, "Alpine");
    page.check("jq", true);
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version current --jq"));

    page.check("java", true);
    assertJavaControls(page, true);
    assert.equal(page.byId("command").value, expectedCommand("--os alpine --version current --java-latest --maven --gradle --jq"));
    assert.equal(page.byId("summary").textContent, "Alpine · Java 27 (latest) · Maven · Gradle · jq");
  });

  test(`${backend}: Clojure alone enables Java versions and build tools`, () => {
    const page = loadPage(backend);
    page.check("java", false);
    assertJavaControls(page, false);
    page.check("clojure", true);
    assertJavaControls(page, true);
    page.check("maven", true);
    page.check("gradle", true);
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts --java-lts --maven --gradle --clojure"));
    page.radio("java-version", "java-latest");
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts --java-latest --maven --gradle --clojure"));
    page.check("java", true);
    page.check("clojure", false);
    assertJavaControls(page, true);
    page.check("java", false);
    assertJavaControls(page, false);
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts"));
  });

  test(`${backend}: reset restores defaults, including retained tools and external force`, () => {
    const page = loadPage(backend);
    page.radio("os", "alpine");
    page.radio("version", "latest");
    page.radio("java-version", "java-latest");
    for (const name of ["maven", "gradle", "clojure", "php", "go", "docker", "force"]) page.check(name, true);
    assert.equal(page.byId("docker-warning").hidden, false);
    assert.ok(page.byId("command").value.endsWith(" --force"));
    page.check("java", false);
    page.check("clojure", false);
    assertJavaControls(page, false);
    page.byId("copy-status").textContent = "Old copy result";

    page.reset();
    assert.equal(page.flag("java").checked, true);
    for (const name of ["maven", "gradle", "clojure", "php", "go", "docker", "force"]) {
      assert.equal(page.flag(name).checked, false, `${name} reset`);
    }
    assertJavaControls(page, true);
    assert.equal(page.byId("command").value, expectedCommand("--os ubuntu --version lts --java-lts"));
    assert.equal(page.byId("image").textContent, "ubuntu:26.04");
    assert.equal(page.byId("summary").textContent, "Ubuntu · Java 25 LTS");
    assert.equal(page.byId("docker-warning").hidden, true);
    assert.equal(page.byId("copy-status").textContent, "");
  });

  test(`${backend}: buildCommand validates options and conflicting Java selections`, () => {
    const { buildCommand } = loadPage(backend);
    assert.equal(buildCommand("alpine", "current", ["java-latest", "maven", "gradle"]),
      expectedCommand("--os alpine --version current --java-latest --maven --gradle"));
    assert.equal(buildCommand("alpine", "latest", []), expectedCommand("--os alpine --version latest"));
    for (const args of [
      ["debian", "current", []], ["__proto__", "current", []],
      ["alpine", "lts", []], ["alpine", "current; touch INJECTED", []],
      ["ubuntu", "lts", ["unknown"]], ["ubuntu", "lts", ["__proto__"]],
      ["ubuntu", "lts", ["maven; touch INJECTED"]],
    ]) {
      assert.throws(() => buildCommand(...args), /Unknown generator option/);
    }
    for (const flags of [["java", "java-lts"], ["java", "java-latest"], ["java-lts", "java-latest"]]) {
      for (const order of [flags, [...flags].reverse()]) {
        assert.throws(() => buildCommand("alpine", "current", order), /mutually exclusive/);
      }
    }
  });
}
