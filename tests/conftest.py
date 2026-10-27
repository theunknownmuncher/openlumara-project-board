# -- AI-GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) status:reviewed harness:openlumara --
# project-board tests for OpenLumara — a kanban / scrum board you drive from the WebUI while your AI drives it with tools
# Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:reviewed
"""
Shared fixtures for the project-board test suite.

The suite is self-contained on purpose: this module lives in user_modules/, so it
ships its own copy of the two things the core test suite does with conftest.py -
redirecting the data folder / config away from a live install, and a minimal fake
manager. Run it from the repository root:

    pytest user_modules/project-board/tests
"""

import asyncio
import importlib
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2].parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core  # noqa: E402


class FakeManager:
    """just enough of core.manager.Manager for a Module: log(), channels, and the
    active channel used by the webui broadcast helper (None: broadcasts no-op)."""

    def __init__(self):
        self.modules = {}
        self.channels = {}
        self.channel = None
        self.logs = []

    def log(self, category, message):
        self.logs.append((category, message))

    def log_error(self, message, e):
        self.logs.append((message, e))


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """
    keeps the suite out of a real install: the data folder, the global config file
    and the module schema cache all point into tmp_path.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    test_config = core.storage.StorageDict(
        "config", "yaml", path=str(tmp_path), override_temporary=True
    )
    test_config.load({"core": {"data_folder": str(data_dir)}})

    monkeypatch.setattr(core.config, "config", test_config)
    monkeypatch.setattr(core.config, "SCHEMA_CACHE_FILE", str(tmp_path / "module_cache.json"))
    monkeypatch.setattr(core.config, "_registry_cache", None)
    monkeypatch.setattr(core.manager, "global_instance", None)

    yield data_dir


@pytest.fixture
def board_manager():
    return FakeManager()


@pytest.fixture
def make_board(isolated_paths):
    """builds a board on top of chosen settings through the real config path, so a test
    can watch a setting do its job (or watch old storage get migrated into a board)"""
    def build(**settings):
        core.config.config.load({
            "core": {"data_folder": str(isolated_paths)},
            "modules": {"settings": {"project-board": dict(settings)}},
        })

        module = importlib.import_module("user_modules.project-board")
        instance = module.ProjectBoard(FakeManager())

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(instance.on_ready())
        finally:
            loop.close()

        return instance

    return build


@pytest.fixture
def board(board_manager):
    """a ProjectBoard with its storage created fresh in the tmp data folder"""
    module = importlib.import_module("user_modules.project-board")

    instance = module.ProjectBoard(board_manager)

    # on_ready() is what normally opens the storage and seeds the columns. It is
    # synchronous in practice, so a throwaway loop is enough here.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(instance.on_ready())
    finally:
        loop.close()

    return instance
