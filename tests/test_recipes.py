import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"
sys.path.insert(0, str(APPS))

from BillCollectorRecipes import CheckRecipe, is_yaml_file  # noqa: E402
from BillCollectorServices import (  # noqa: E402
    ACTION_MAP,
    perform__switch_to_default_frame,
    perform__switch_to_parent_frame,
)


class RecipeValidationTests(unittest.TestCase):
    def test_all_bundled_recipes_match_the_schema(self):
        recipes = sorted((APPS / "bc-recipes").glob("bc-recipe__*.yaml"))
        self.assertTrue(recipes, "No bundled recipes were found")

        for recipe in recipes:
            with self.subTest(recipe=recipe.name):
                self.assertIsNotNone(CheckRecipe(recipe))

    def test_every_schema_action_has_a_runtime_handler(self):
        schema_path = APPS / "bc-recipes" / "bc-recipe-schema.yaml"
        with schema_path.open(encoding="utf-8") as stream:
            schema = yaml.safe_load(stream)

        action_types = set(
            schema["properties"]["services"]["items"]["properties"]["actions"]
            ["items"]["properties"]["actionType"]["enum"]
        )
        self.assertEqual(action_types, set(ACTION_MAP))

    def test_invalid_yaml_returns_a_validation_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            malformed = Path(temp_dir) / "malformed.yaml"
            malformed.write_text("services: [\n", encoding="utf-8")
            with malformed.open(encoding="utf-8") as stream:
                valid, parsed = is_yaml_file(stream)

        self.assertFalse(valid)
        self.assertIsNone(parsed)

    @patch("BillCollectorServices.time.sleep", return_value=None)
    def test_parameterless_frame_switch_actions(self, _sleep):
        browser = SimpleNamespace(dbg=False, drv=MagicMock())

        perform__switch_to_parent_frame(browser, None)
        perform__switch_to_default_frame(browser, None)

        browser.drv.switch_to.parent_frame.assert_called_once_with()
        browser.drv.switch_to.default_content.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
