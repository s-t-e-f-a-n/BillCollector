import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"
sys.path.insert(0, str(APPS))

from BillCollectorRecipes import CheckRecipe, is_yaml_file  # noqa: E402
from BillCollectorServices import ACTION_MAP  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
