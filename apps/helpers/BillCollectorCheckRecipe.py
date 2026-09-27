import os
import sys
import logging
import yaml
import jsonschema
from jsonschema import validate, ValidationError
from helpers import *

logger = logging.getLogger(__name__)

def get_schema_for_yaml(yaml_file):
    try:
        with open(yaml_file, "r") as yf:
            yml = yaml.safe_load(yf)
            return yml.get("$schema", None)
    except yaml.YAMLError:
        logger.error(f"File {yaml_file} not valid YAML.")
        return None
    except OSError:
        logger.error(f"File {yaml_file} not found.")
        return None

def is_yaml_file(stream):
    try:
        yml = yaml.safe_load(stream)  
        return True, yml
    except yaml.YAMLError:
        logger.error(f"File not valid YAML.")
        return False, None
    except FileNotFoundError:
        logger.error(f"File not found.")
        return False, None

# Check if the recipe file is valid
# and if the schema file is valid
# and if the recipe file is valid against the schema
# if no schem_file is given, the schema file is expected by $schema-URI in the recipe file
# if no schema file is found, the recipe file is not valid
def CheckRecipe(recipe_file, schema_file=None):
    if recipe_file == None:
        logger.error("No recipe file given. Exit(1)")
        exit(1)
    if schema_file != None:
        try:
            with open(schema_file, "r") as stream:
                ret, schema = is_yaml_file(stream)
                if ret == False: 
                    logger.error(f"Schema {schema_file} is not a valid BillCollector yaml. Exit(1)")
                    exit(1)
        except OSError:
            logger.error(f"Cannot open {schema_file}. Exit(1)")
            exit(1)
    else:
        schema_file = get_schema_for_yaml(recipe_file)
        if schema_file == None: 
            logger.error(f"No schema file found. Exit(1)")
            exit(1)
        else:
            schema_file=os.path.join(os.path.dirname(recipe_file), os.path.basename(schema_file))
            return (CheckRecipe(recipe_file, schema_file))
    try:
        with open(recipe_file, "r") as stream:
            ret, recipe = is_yaml_file(stream)
        if ret == False: raise Exception("{recipe_file} is not a valid BillCollector yaml.")
    except OSError:
        logger.error(f"Cannot open {recipe_file}.")
        return None
    try:
        validate(instance=recipe, schema=schema)
        logger.debug(f"Recipe {recipe_file} is a valid BillCollector yaml!")
        return recipe
    except ValidationError as e:
        logger.error(f"Validation fault: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error: {e}")
        return None

if __name__ == "__main__":
    sys.stdout = sys.__stdout__
    setup_logging()
    schema_file = None
    if is_debug_session():
        logger.info("Executed in debugger.")
        recipe_file=os.path.join(RECIPES_PLAYWRIGHT_DIR, "recipe-pw__winsim.yaml")
    else:
        logger.info("Executed from command line.")
        if len(sys.argv) < 2 or len(sys.argv) > 3:
            logger.error(" Usage: python3 BillCollectorRecipes.py <recipes.yaml> <schema.yaml>")
            sys.exit(1)
        recipe_file = sys.argv[1]
        if len(sys.argv) == 3:
            schema_file = sys.argv[2]
    if schema_file != None:
        CheckRecipe(recipe_file, schema_file)
    else:
        CheckRecipe(recipe_file)
    sys.exit(0)
