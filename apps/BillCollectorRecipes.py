import os
import sys
import yaml
from jsonschema import validate, ValidationError

def is_yaml_file(stream):
    try:
        yml = yaml.safe_load(stream)  
        return True, yml
    except yml.YAMLError:
        print(f"File not valid YAML.")
        return False, None
    except FileNotFoundError:
        print(f"File not found.")
        return False, None

def CheckRecipe(recipe_file, schema_file=os.path.join(os.path.dirname(__file__), "bc-recipes", "bc-recipe-schema.yaml")):
    try:
        with open(schema_file, "r") as stream:
            ret, schema = is_yaml_file(stream)
            if ret == False: 
                print(f"Schema {schema_file} is not a valid BillCollector yaml. Exit(1)")
                exit(1)
    except OSError:
        print(f"Cannot open {schema_file}.")
        return None
    try:
        with open(recipe_file, "r") as stream:
            ret, recipe = is_yaml_file(stream)
        if ret == False: raise Exception("{recipe_file} is not a valid BillCollector yaml.")
    except OSError:
        print(f"Cannot open {recipe_file}.")
        return None
    try:
        validate(instance=recipe, schema=schema)
        print(f"Recipe {recipe_file} is a valid BillCollector yaml!")
        return recipe
    except ValidationError as e:
        print("Validation fault:", e)
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    sys.stdout = sys.__stdout__
    schema_file = None
    if sys.gettrace():
        print("Executed in debugger.")
        recipe_file=os.path.join(os.path.dirname(__file__), "bc-recipes", "bc-recipe-test.yaml")
    else:
        print("Executed from command line.")
        if len(sys.argv) < 2 or len(sys.argv) > 3:
            print(" Usage: python3 BillCollectorRecipes.py <recipes.yaml> [<schema.yaml>]")
            sys.exit(1)
        recipe_file = sys.argv[1]
        if len(sys.argv) == 3:
            schema_file = sys.argv[2]
    if schema_file != None:
        CheckRecipe(recipe_file, schema_file)
    else:
        CheckRecipe(recipe_file)
    sys.exit(0)
else:
    print(f"{__name__} imported as module.")
