import subprocess
import re
import json
from dockerfile_parse import DockerfileParser
from versions.package import Package
from versions.pypi import version_pypi
from versions.alpine import version_alpine
from versions.debian import version_debian
from versions.docker import get_docker_tags
from helpers import get_packages


class Dockerfile:
    def __init__(self, config, filepath):
        self.changed = False
        self.config = config
        self.content = ""
        self.filepath = filepath
        self.filepathmin = filepath.replace(config.rootdir, "")
        self.get_content()

    def get_structure(self):
        dfp = DockerfileParser()
        dfp.content = self.content

        RUN, FROM, ARG = [], [], []
        for item in json.loads(dfp.json):
            if item.get("RUN"):
                for run in item["RUN"].split("&&"):
                    RUN.append(run)
            elif item.get("FROM"):
                FROM.append(item["FROM"])
            elif item.get("ARG"):
                ARG.append(item["ARG"])
        return FROM, ARG, RUN

    def commit(self, package, installed, available):
        subprocess.run(["git", "add", self.filepath])
        msg = self.config.commit_msg
        msg = msg.replace("[package]", package)
        msg = msg.replace("[from_version]", installed)
        msg = msg.replace("[to_version]", available)
        subprocess.run(["git", "commit", "-m", msg])
        with open(f"{self.config.rootdir}/changes", "a") as changes:
            changes.write(f"- {msg}\n")
        self.changed = True

    def get_content(self):
        with open(self.filepath, "r") as f:
            content = f.read()
        self.content = content

    def write_content(self):
        with open(self.filepath, "w") as f:
            f.write(self.content)

    def update(self):
        print(f"Checking for updates in '{self.filepathmin}'")
        x, y, z = self.get_structure()
        structure = {"from": x, "arg": y, "run": z}
        if not structure.get("run"):
            return

        print(f"exclude_type: {self.config.exclude_type}")
        if "base" not in self.config.exclude_type:
            self.update_base_image(structure)
        if "pip" not in self.config.exclude_type:
            self.update_pip_packages(structure)
        if "apk" not in self.config.exclude_type:
            self.update_alpine_packages(structure)
        # if "apt" not in self.config.exclude_type:
        #    self.update_debian_packages(structure)

        return self.changed

    def update_base_image(self, structure):
        installed = structure.get("from")[0].strip()
        available = None
        image = None
        print(f"installed: {structure}")
        if ":" not in installed:
            return
        if "alpine" in installed:
            image = "alpine"
            if len(installed.split(":")[-1].split(".")) != 3:
                return
            for tag in get_docker_tags(image):
                if len(tag["name"].split(".")) == 3:
                    available = f"alpine:{tag['name']}"
                    break

        if "debian" in installed:
            image = "debian"
            if len(installed.split(":")[-1].split(".")) != 2:
                return
            for tag in sorted(get_docker_tags(image), reverse=True):
                if "-slim" in installed:
                    if (
                        len(tag.split(".")) == 2
                        and "-slim" in tag
                        and int(tag.split(".")[0]) >= 10
                    ):
                        available = f"debian:{tag}"
                        break
                else:
                    if (
                        len(tag.split(".")) == 2
                        and "-slim" not in tag
                        and int(tag.split(".")[0]) >= 10
                    ):
                        available = f"debian:{tag}"
                        break

        if available is not None and image is not None:
            if available != installed:
                self.get_content()
                self.content = self.content.replace(installed, available)
                self.write_content()
                self.commit(image, installed.split(
                    ":")[-1], available.split(":")[-1])

    def update_pip_packages(self, structure):
        for package in get_packages(structure)["pypi"]:
            if "==" not in package.old:
                continue
            if package.name in self.config.exclude_package:
                continue
            package.available = version_pypi(package.name)
            if package.updated:
                self.get_content()
                self.content = self.content.replace(package.old, package.new)
                self.write_content()
                self.commit(package.name, package.installed, package.available)

    def update_alpine_packages(self, structure):
        for package in get_packages(structure)["alpine"]:
            if "==" not in package.old:
                package.available = version_alpine(package.name)
                if package.updated:
                    self.get_content()
                    self.content = self.content.replace(
                        package.old, package.new)
                    self.write_content()
                    self.commit(package.name, package.installed,
                                package.available)

    def update_debian_packages(self, structure):
        for package in get_packages(structure)["debian"]:
            if "==" not in package.old:
                package.available = version_debian(package.name)
                if package.updated:
                    self.get_content()
                    self.content = self.content.replace(
                        package.old, package.new)
                    self.write_content()
                    self.commit(package.name, package.installed,
                                package.available)
