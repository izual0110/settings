"""Offline integration tests for the standalone Bash devcontainer generator."""

import itertools
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "generate-devcontainer.sh"
BASH = shutil.which("bash")
RELEASES = {
    "ubuntu": {
        "lts": "26.04",
        "current": "26.04",
        "latest": "latest",
        "22.04": "22.04",
        "24.04": "24.04",
        "26.04": "26.04",
    },
    "fedora": {"current": "44", "latest": "latest", "44": "44"},
}
LANGUAGES = {
    "ubuntu": {"php": "php-cli", "go": "golang-go"},
    "fedora": {"php": "php-cli", "go": "golang"},
}
JAVA_PACKAGES = {
    "ubuntu": {"fontconfig", "libstdc++6", "tzdata", "zlib1g", "binutils"},
    "fedora": {"fontconfig", "libstdc++", "tzdata", "zlib", "binutils"},
}
EXTRAS = ("docker", "build-tools", "jq", "unzip")


@unittest.skipUnless(BASH, "Bash is required")
class GenerateDevcontainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="devcontainer tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_generator(self, *args, piped=False, source=None):
        env = os.environ.copy()
        env.pop("BASH_ENV", None)
        env.pop("ENV", None)
        if piped:
            command = [BASH, "-s", "--", *args]
            if source is None:
                source = SCRIPT.read_text()
        else:
            command = [BASH, str(SCRIPT), *args]
        return subprocess.run(
            command,
            cwd=str(self.root),
            input=source,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
            env=env,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def read_output(self, output=".devcontainer"):
        directory = self.root / output
        self.assertEqual(
            {entry.name for entry in directory.iterdir()},
            {"Dockerfile", "devcontainer.json"},
        )
        dockerfile = (directory / "Dockerfile").read_text()
        config = json.loads((directory / "devcontainer.json").read_text())
        self.assertEqual(
            config["name"],
            "Development container for ${localWorkspaceFolderBasename}",
        )
        self.assertEqual(config["build"], {"dockerfile": "Dockerfile"})
        self.assertEqual(config["workspaceFolder"], "/workspace")
        self.assertEqual(
            config["workspaceMount"],
            "source=${localWorkspaceFolder},target=/workspace,type=bind",
        )
        self.assertEqual(config["shutdownAction"], "stopContainer")
        self.assertIn("WORKDIR /workspace\n", dockerfile)
        self.assertIn('CMD ["sleep", "infinity"]\n', dockerfile)
        self.assertIn("git config --system --add safe.directory /workspace", dockerfile)
        self.assertNotIn("safe.directory '*'", dockerfile)
        self.assertNotIn("privileged", config)
        # Check the generated RUN commands with the portable shell parser too.
        instructions = dockerfile.replace("\\\n", " ").splitlines()
        for instruction in instructions:
            if instruction.startswith("RUN "):
                parsed = subprocess.run(
                    ["/bin/sh", "-n"],
                    input=instruction[4:],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)
        return dockerfile, config

    @staticmethod
    def installed_packages(dockerfile):
        line = next(line for line in dockerfile.splitlines() if "install -y " in line)
        words = shlex.split(line.split("install -y ", 1)[1].rstrip().rstrip("\\"))
        return set(words) - {"--no-install-recommends", "$compose_package"}

    def assert_base(self, dockerfile, os_name, tag):
        image = "ubuntu" if os_name == "ubuntu" else "quay.io/fedora/fedora"
        self.assertTrue(dockerfile.startswith(f"FROM {image}:{tag}\n"))
        packages = self.installed_packages(dockerfile)
        base = {"bash", "ca-certificates", "curl", "git", "tar", "gzip", "findutils"}
        base.add("procps" if os_name == "ubuntu" else "procps-ng")
        self.assertTrue(base <= packages, packages)
        if os_name == "ubuntu":
            self.assertIn("apt-get update", dockerfile)
            self.assertIn("DEBIAN_FRONTEND=noninteractive", dockerfile)
            self.assertIn("rm -rf /var/lib/apt/lists/*", dockerfile)
            self.assertNotIn("dnf", dockerfile)
        else:
            self.assertIn("dnf install -y", dockerfile)
            self.assertIn("dnf clean all", dockerfile)
            self.assertNotIn("apt-get", dockerfile)
        return base

    def test_defaults(self):
        self.assert_success(self.run_generator())
        dockerfile, config = self.read_output()
        base = self.assert_base(dockerfile, "ubuntu", "26.04")
        self.assertEqual(self.installed_packages(dockerfile), base)
        self.assertNotIn("mounts", config)
        self.assertNotIn("docker.sock", json.dumps(config))

    def test_default_versions_are_conditional_and_argument_order_independent(self):
        cases = [
            (["--os", "ubuntu"], "ubuntu", "26.04"),
            (["--os", "fedora"], "fedora", "44"),
            (["--version", "current", "--os", "fedora"], "fedora", "44"),
            (["--version", "latest", "--os", "ubuntu"], "ubuntu", "latest"),
        ]
        for number, (args, os_name, tag) in enumerate(cases):
            with self.subTest(args=args):
                output = f"default-{number}"
                self.assert_success(self.run_generator(*args, "--output", output))
                dockerfile, config = self.read_output(output)
                base = self.assert_base(dockerfile, os_name, tag)
                self.assertEqual(self.installed_packages(dockerfile), base)
                self.assertNotIn("mounts", config)

    def assert_java(self, dockerfile, version):
        self.assertIn(
            f"COPY --from=eclipse-temurin:{version}-jdk /opt/java/openjdk /opt/java/openjdk",
            dockerfile,
        )
        self.assertEqual(dockerfile.count("COPY --from=eclipse-temurin:"), 1)
        self.assertIn("ENV JAVA_HOME=/opt/java/openjdk", dockerfile)
        self.assertIn('ENV PATH="${JAVA_HOME}/bin:${PATH}"', dockerfile)
        self.assertIn("RUN java --version && javac --version", dockerfile)

    def test_all_language_combinations_for_every_release_and_alias(self):
        names = ("java", "php", "go", "clojure")
        number = 0
        for os_name, releases in RELEASES.items():
            for version, tag in releases.items():
                for enabled in itertools.product((False, True), repeat=len(names)):
                    with self.subTest(os=os_name, version=version, languages=enabled):
                        output = f"languages-{number}"
                        number += 1
                        selected = {name for name, value in zip(names, enabled) if value}
                        flags = ["--" + name for name in names if name in selected]
                        self.assert_success(self.run_generator(
                            "--os", os_name, "--version", version,
                            "--output", output, *flags,
                        ))
                        dockerfile, config = self.read_output(output)
                        expected = self.assert_base(dockerfile, os_name, tag)
                        expected.update(
                            LANGUAGES[os_name][name]
                            for name in ("php", "go") if name in selected
                        )
                        if selected & {"java", "clojure"}:
                            expected.update(JAVA_PACKAGES[os_name])
                            self.assert_java(dockerfile, "25")
                        else:
                            self.assertNotIn("eclipse-temurin", dockerfile)
                        if "clojure" in selected:
                            expected.add("rlwrap")
                            self.assertIn("ARG CLOJURE_VERSION=1.12.6.1673", dockerfile)
                            self.assertIn(
                                "https://github.com/clojure/brew-install/releases/download/"
                                "${CLOJURE_VERSION}/linux-install.sh", dockerfile,
                            )
                            self.assertIn("&& cd /tmp", dockerfile)
                            self.assertIn("&& bash linux-install.sh", dockerfile)
                            self.assertIn("&& rm -f linux-install.sh", dockerfile)
                            self.assertIn("&& clojure -Sdescribe", dockerfile)
                        else:
                            self.assertNotIn("CLOJURE_VERSION", dockerfile)
                        self.assertEqual(self.installed_packages(dockerfile), expected)
                        self.assertNotIn("mounts", config)

    def test_java_modes_with_and_without_clojure_for_every_release(self):
        number = 0
        for os_name, releases in RELEASES.items():
            for version, tag in releases.items():
                for flag, java_version in (("--java", "25"), ("--java-lts", "25"),
                                           ("--java-latest", "27")):
                    for clojure in (False, True):
                        with self.subTest(os=os_name, version=version, java=flag, clojure=clojure):
                            output = f"java-modes-{number}"
                            number += 1
                            # Exercise both argument orders for the automatic JDK selection.
                            args = [flag]
                            if clojure:
                                args = ["--clojure", flag] if number % 2 else [flag, "--clojure"]
                            self.assert_success(self.run_generator(
                                "--os", os_name, "--version", version,
                                "--output", output, *args,
                            ))
                            dockerfile, _ = self.read_output(output)
                            expected = self.assert_base(dockerfile, os_name, tag)
                            expected.update(JAVA_PACKAGES[os_name])
                            if clojure:
                                expected.add("rlwrap")
                            self.assert_java(dockerfile, java_version)
                            self.assertEqual(self.installed_packages(dockerfile), expected)

    def test_repeated_same_java_mode_is_allowed(self):
        self.assert_success(self.run_generator("--java-lts", "--java", "--java-lts"))
        dockerfile, _ = self.read_output()
        self.assert_java(dockerfile, "25")

    def test_ai_tools_for_every_release_with_each_java_mode(self):
        number = 0
        for os_name, releases in RELEASES.items():
            for version, tag in releases.items():
                for claude, codex in itertools.product((False, True), repeat=2):
                    for java in (None, "--java-lts", "--java-latest"):
                        with self.subTest(os=os_name, version=version, claude=claude,
                                          codex=codex, java=java):
                            output = f"ai-tools-{number}"
                            number += 1
                            flags = []
                            if claude:
                                flags.append("--claude")
                            if codex:
                                flags.append("--codex")
                            if java:
                                flags.append(java)
                            self.assert_success(self.run_generator(
                                "--os", os_name, "--version", version,
                                "--output", output, *flags,
                            ))
                            dockerfile, config = self.read_output(output)
                            expected = self.assert_base(dockerfile, os_name, tag)
                            if java:
                                expected.update(JAVA_PACKAGES[os_name])
                                self.assert_java(dockerfile, "25" if java == "--java-lts" else "27")
                            else:
                                self.assertNotIn("eclipse-temurin", dockerfile)
                            if claude or codex:
                                self.assertIn('ENV PATH="/root/.local/bin:${PATH}"', dockerfile)
                            else:
                                self.assertNotIn("/root/.local/bin", dockerfile)
                            if claude:
                                expected.add("libstdc++6" if os_name == "ubuntu" else "libstdc++")
                                self.assertIn("https://claude.ai/install.sh", dockerfile)
                                self.assertIn("&& bash /tmp/claude-install.sh latest", dockerfile)
                                self.assertIn("&& rm -f /tmp/claude-install.sh", dockerfile)
                                self.assertIn("&& claude --version", dockerfile)
                            else:
                                self.assertNotIn("claude-install.sh", dockerfile)
                            if codex:
                                expected.add("mawk" if os_name == "ubuntu" else "gawk")
                                self.assertIn("https://chatgpt.com/codex/install.sh", dockerfile)
                                self.assertIn("&& CODEX_NON_INTERACTIVE=true sh /tmp/codex-install.sh", dockerfile)
                                self.assertIn("&& rm -f /tmp/codex-install.sh", dockerfile)
                                self.assertIn("&& codex --version", dockerfile)
                            else:
                                self.assertNotIn("codex-install.sh", dockerfile)
                            self.assertEqual(self.installed_packages(dockerfile), expected)
                            self.assertNotIn("npm", dockerfile)
                            self.assertNotIn("ANTHROPIC_API_KEY", dockerfile)
                            self.assertNotIn("OPENAI_API_KEY", dockerfile)
                            self.assertNotIn("mounts", config)

    def test_ai_flags_can_be_repeated_without_duplicate_installers(self):
        self.assert_success(self.run_generator("--claude", "--codex", "--claude", "--codex"))
        dockerfile, _ = self.read_output()
        self.assertEqual(dockerfile.count("https://claude.ai/install.sh"), 1)
        self.assertEqual(dockerfile.count("https://chatgpt.com/codex/install.sh"), 1)

    def test_all_extra_toggle_combinations_for_each_distro(self):
        for os_name in RELEASES:
            for number, enabled in enumerate(itertools.product((False, True), repeat=len(EXTRAS))):
                with self.subTest(os=os_name, extras=enabled):
                    output = f"extras-{os_name}-{number}"
                    flags = ["--" + name for name, value in zip(EXTRAS, enabled) if value]
                    self.assert_success(self.run_generator(
                        "--os", os_name, "--output", output, *flags,
                    ))
                    dockerfile, config = self.read_output(output)
                    expected = self.assert_base(
                        dockerfile, os_name, "26.04" if os_name == "ubuntu" else "44",
                    )
                    if enabled[0]:
                        expected.update(
                            ("docker.io", "docker-compose-v2") if os_name == "ubuntu"
                            else ("docker-cli", "docker-compose")
                        )
                        self.assertEqual(config["mounts"], [
                            "source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"
                        ])
                    else:
                        self.assertNotIn("mounts", config)
                        self.assertNotIn("docker.sock", json.dumps(config))
                    if enabled[1]:
                        expected.update(
                            ("build-essential",) if os_name == "ubuntu"
                            else ("gcc", "gcc-c++", "make")
                        )
                    expected.update(name for name, value in zip(EXTRAS[2:], enabled[2:]) if value)
                    self.assertEqual(self.installed_packages(dockerfile), expected)

    def test_docker_for_every_release_including_jammy_compose_fallback(self):
        for os_name, releases in RELEASES.items():
            for version, tag in releases.items():
                with self.subTest(os=os_name, version=version):
                    output = f"docker-{os_name}-{version}"
                    self.assert_success(self.run_generator(
                        "--os", os_name, "--version", version, "--docker", "--output", output,
                    ))
                    dockerfile, config = self.read_output(output)
                    self.assert_base(dockerfile, os_name, tag)
                    self.assertIn("docker.sock", config["mounts"][0])
                    if os_name == "ubuntu" and tag == "22.04":
                        self.assertIn("apt-cache show docker-compose-v2", dockerfile)
                        self.assertIn("compose_package=docker-compose-v2", dockerfile)
                        self.assertIn("else compose_package=docker-compose; fi", dockerfile)
                        self.assertIn('"$compose_package"', dockerfile)
                    elif os_name == "ubuntu":
                        self.assertIn("docker-compose-v2", self.installed_packages(dockerfile))
                    else:
                        self.assertIn("docker-compose", self.installed_packages(dockerfile))

    def test_invalid_arguments_do_not_write(self):
        cases = [
            ["--unknown"], ["ubuntu"], ["--"], ["--os=ubuntu"], ["--java=true"],
            ["--vim"], ["--tmux"],
            ["--os"], ["--version"], ["--output"],
            ["--os", ""], ["--version", ""], ["--output", ""],
            ["--os", "--java"], ["--version", "--go"], ["--output", "--force"],
            ["--os", "debian"], ["--os", "Ubuntu"],
            ["--version", "44"], ["--version", "20.04"],
            ["--version", "26.04; touch INJECTED"],
            ["--os", "fedora", "--version", "lts"],
            ["--os", "fedora", "--version", "26.04"],
            ["--os", "fedora", "--version", "43"],
            ["--java", "false"], ["--output", "valid", "--bad"],
            ["--java-lts", "--java-latest"], ["--java-latest", "--java-lts"],
            ["--java", "--java-latest"], ["--java-latest", "--java"],
            ["--clojure", "--java-latest", "--java-lts"],
            ["--java-lts", "25"], ["--java-latest", "27"], ["--clojure=true"],
            ["--claude=true"], ["--codex=true"], ["--claude", "false"], ["--codex", "false"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_generator(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Error:", result.stderr)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_help_has_no_side_effects(self):
        for args in (["--help"], ["--output", "unused", "--help"]):
            result = self.run_generator(*args)
            self.assert_success(result)
            self.assertIn("Usage:", result.stdout)
            self.assertNotIn("--vim", result.stdout)
            self.assertNotIn("--tmux", result.stdout)
            for option in ("os", "version", "java", "java-lts", "java-latest", "clojure",
                           "php", "go", "claude", "codex", *EXTRAS, "force", "output"):
                self.assertIn("--" + option, result.stdout)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_refusal_preserves_both_files_and_does_not_create_missing_peer(self):
        for number, existing in enumerate((
            ("Dockerfile",), ("devcontainer.json",), ("Dockerfile", "devcontainer.json"),
        )):
            with self.subTest(existing=existing):
                output = self.root / f"existing-{number}"
                output.mkdir()
                for name in existing:
                    (output / name).write_text("original " + name)
                result = self.run_generator("--output", str(output), "--java")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--force", result.stderr)
                self.assertEqual({p.name for p in output.iterdir()}, set(existing))
                for name in existing:
                    self.assertEqual((output / name).read_text(), "original " + name)

    def test_force_replaces_regular_files_and_keeps_unrelated_files(self):
        output = self.root / "existing"
        output.mkdir()
        (output / "Dockerfile").write_text("old Dockerfile")
        (output / "devcontainer.json").write_text("old config")
        (output / "keep.txt").write_text("untouched")
        self.assert_success(self.run_generator("--output", str(output), "--force", "--java"))
        self.assert_java((output / "Dockerfile").read_text(), "25")
        self.assertEqual(json.loads((output / "devcontainer.json").read_text())["workspaceFolder"], "/workspace")
        self.assertEqual((output / "keep.txt").read_text(), "untouched")
        self.assertEqual({p.name for p in output.iterdir()}, {"Dockerfile", "devcontainer.json", "keep.txt"})

    def test_force_also_works_when_files_do_not_exist(self):
        self.assert_success(self.run_generator("--force"))
        self.read_output()

    def test_symlinks_and_directories_are_refused_even_with_force(self):
        for target_name in ("Dockerfile", "devcontainer.json"):
            for kind in ("symlink", "dangling", "directory"):
                for force in (False, True):
                    with self.subTest(target=target_name, kind=kind, force=force):
                        output = self.root / f"{target_name}-{kind}-{force}"
                        output.mkdir()
                        peer_name = "devcontainer.json" if target_name == "Dockerfile" else "Dockerfile"
                        (output / peer_name).write_text("preserve peer")
                        target = output / target_name
                        destination = self.root / f"{output.name}-destination"
                        if kind == "directory":
                            target.mkdir()
                            (target / "keep").write_text("keep directory")
                        else:
                            if kind == "symlink":
                                destination.write_text("preserve destination")
                            target.symlink_to(destination)
                        args = ["--output", str(output)] + (["--force"] if force else [])
                        result = self.run_generator(*args)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual((output / peer_name).read_text(), "preserve peer")
                        self.assertEqual({p.name for p in output.iterdir()}, {target_name, peer_name})
                        if kind == "directory":
                            self.assertEqual((target / "keep").read_text(), "keep directory")
                        else:
                            self.assertTrue(target.is_symlink())
                            if kind == "symlink":
                                self.assertEqual(destination.read_text(), "preserve destination")
                            else:
                                self.assertFalse(destination.exists())

    def test_invalid_output_directory_is_refused(self):
        regular = self.root / "regular"
        regular.write_text("preserve regular")
        destination = self.root / "destination"
        destination.mkdir()
        link = self.root / "link"
        link.symlink_to(destination, target_is_directory=True)
        for output in (str(regular), str(link), str(link) + "/"):
            for force in (False, True):
                with self.subTest(output=output, force=force):
                    args = ["--output", output] + (["--force"] if force else [])
                    self.assertNotEqual(self.run_generator(*args).returncode, 0)
                    self.assertEqual(regular.read_text(), "preserve regular")
                    self.assertEqual(list(destination.iterdir()), [])
                    self.assertTrue(link.is_symlink())

    def test_paths_with_spaces_leading_dash_and_shell_metacharacters(self):
        for output in ("nested parent/output folder", "-leading-dash", "literal; touch INJECTED", "quote'and\"dollar$()"):
            with self.subTest(output=output):
                self.assert_success(self.run_generator("--output", output, "--go"))
                self.read_output(output)
                self.assertFalse((self.root / "INJECTED").exists())
        self.assert_success(self.run_generator("--output", "trailing slash///"))
        self.read_output("trailing slash")

    def test_piped_bash_s_invocation_and_literal_workspace_token(self):
        result = self.run_generator(
            "--os", "fedora", "--version", "latest", "--java", "--php", "--go",
            "--docker", "--output", "piped output", piped=True,
        )
        self.assert_success(result)
        dockerfile, config = self.read_output("piped output")
        self.assert_base(dockerfile, "fedora", "latest")
        self.assertIn("${localWorkspaceFolder}", config["workspaceMount"])
        self.assertTrue(set(LANGUAGES["fedora"].values()) <= self.installed_packages(dockerfile))

    def test_downloaded_prefix_has_no_side_effects(self):
        source = SCRIPT.read_text().rsplit('main "$@"', 1)[0]
        self.assert_success(self.run_generator(piped=True, source=source))
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
