# Settings

Personal configuration files for [Zed](zed/), [VS Code](vs%20code/), and [tmux](tmux/).

## Devcontainer builder

Open [index.html](index.html) in a browser to configure an Ubuntu or Fedora development container. No build step required.

Run the generator from your project's root directory:

```sh
bash /path/to/settings/generate-devcontainer.sh --os ubuntu --java-lts --clojure
```

Creates `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json`. Then reopen the project in a Dev Containers-compatible editor.

Use `--help` for all options or `--force` to replace existing generated files.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
