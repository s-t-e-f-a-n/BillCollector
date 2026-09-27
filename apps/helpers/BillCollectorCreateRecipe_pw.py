import sys
import os
import subprocess
import re
import logging
import yaml
import argparse

from BillCollectorHelpers import *

logger = logging.getLogger(__name__)

# --- YAML helper classes for double-quoted strings ---
class DoubleQuoted(str):
    pass

class CustomDumper(yaml.SafeDumper):
    pass

def represent_double_quoted(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')

CustomDumper.add_representer(DoubleQuoted, represent_double_quoted)

def wrap_str(s):
    # Ensure double quotes are preserved correctly without unnecessary escaping
    if s.startswith('"') and s.endswith('"'):
        return DoubleQuoted(s)  # Preserve the original format
    return DoubleQuoted(s.replace('\\"', '"'))  # Clean up extra escaping

def parse_kwargs(s):
    """Parse key=value pairs from a string, handling quoted strings and boolean values."""
    kwargs_list = []
    pattern = re.compile(r'(\w+)\s*=\s*("([^"]+)"|(\w+))')
    for m in pattern.finditer(s):
        key = m.group(1)
        value_raw = m.group(3) or m.group(4)
        if m.group(3):
            value = wrap_str(value_raw)
        elif value_raw.lower() in ["true", "false"]:
            value = value_raw.lower() == "true"
        elif value_raw.isdigit():
            value = int(value_raw)
        else:
            try:
                value = float(value_raw)
            except ValueError:
                value = value_raw
        kwargs_list.append({key: value})
    # If no key/value pairs but the string is entirely quoted, treat it as a single "value"
    if not kwargs_list and s.strip().startswith('"') and s.strip().endswith('"'):
        return [{"value": wrap_str(s.strip()[1:-1])}]
    return kwargs_list

def parse_method_arguments(arg_str, method_name, allowed_page_methods):
    """Parse method arguments from a string, handling quoted strings and key=value pairs."""
    arg_str = arg_str.strip()
    if not arg_str:
        return []
    parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', arg_str)
    arg_list = []
    # For the first part: if it's quoted, map it to the primary key; otherwise treat it as key=value.
    first = parts[0].strip()
    if first.startswith('"') and first.endswith('"'):
        key = allowed_page_methods.get(method_name, "value")
        arg_list.append({key: wrap_str(first[1:-1])})
    else:
        arg_list.extend(parse_kwargs(first))
    # Process the remaining parts as key/value pairs.
    for part in parts[1:]:
        part = part.strip()
        if part:
            arg_list.extend(parse_kwargs(part))
    return arg_list

# Global mapping for locator-like methods: determines the key for the primary argument.
allowed_page_methods = {
    "locator": "selector",
    "get_by_role": "role",
    "get_by_title": "text",
    "get_by_label": "text",
    "get_by_text": "text",
    "goto": "url",
    "click": "selector",
    "get_by_placeholder": "text",
    "get_by_test_id": "test_id", 
    "nth": "index"
}

def tokenize_chain(chain):
    """Tokenizer: Splits a dot-separated chain, but does not split on dots inside parentheses."""
    tokens = []
    current = ""
    paren_level = 0
    for ch in chain:
        if ch == '.' and paren_level == 0:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += ch
            if ch == '(':
                paren_level += 1
            elif ch == ')':
                paren_level -= 1
    if current:
        tokens.append(current)
    return tokens

def parse_normal_line(stripped, step_number):
    """Parse a single Playwright line into a step dictionary."""

    # Remove any leading "await "
    if stripped.startswith("await "):
        stripped = stripped[len("await "):].strip()
    # Remove "page." prefix if present
    if stripped.startswith("page."):
        chain = stripped[len("page."):]
    else:
        chain = stripped
    chain = chain.rstrip(";")
    
    tokens = tokenize_chain(chain)
    methods = []
    
    for token in tokens:
        # Check if the token is a method call i.e., contains parentheses at the end.
        m = re.match(r'^(\w+)\(\s*(.*)\s*\)$', token)
        if m:
            name = m.group(1)
            arg_str = m.group(2).strip()
            method_dict = {"method": name}
            if arg_str:
                # Pass the original method name so the lookup works correctly.
                parsed_args = parse_method_arguments(arg_str, name, allowed_page_methods)
                if parsed_args:
                    method_dict["arguments"] = parsed_args
            methods.append(method_dict)
        else:
            # Otherwise, treat it as a property accessor or a no-argument method.
            methods.append({"method": token})
    
    return {
        "step": step_number,
        "description": "",
        "methods": methods
    }

def parse_playwright_script(file_content):
    """Main parser: Processes normal lines and nested expect_download blocks."""

    steps = []
    step_counter = 1
    lines = file_content.splitlines()
    i = 0
    
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        
        stripped = line.strip()
        if stripped.startswith("await "):
            stripped = stripped[len("await "):].strip()
        
        # Handle nested block: with page.expect_download() as ...
        if stripped.startswith("with page.expect_download(") or stripped.startswith("with page.expect_popup("):
            block = {
                "step": step_counter,
                "description": "",
                "methods": [{"method": "expect_download"}],
                "steps": []
            }
            step_counter += 1
            base_indent = len(line) - len(line.lstrip())
            i += 1
            
            # Process lines inside the nested block
            while i < len(lines):
                nested_line = lines[i]
                if not nested_line.strip():
                    i += 1
                    continue
                indent = len(nested_line) - len(nested_line.lstrip())
                if indent <= base_indent:
                    break
                nested_stripped = nested_line.strip()
                if nested_stripped.startswith("await "):
                    nested_stripped = nested_stripped[len("await "):].strip()
                if not nested_stripped.startswith("page."):
                    i += 1
                    continue
                
                nested_step = parse_normal_line(nested_stripped, step_counter)
                step_counter += 1
                block["steps"].append(nested_step)
                i += 1
            
            steps.append(block)
            continue
        
        # Process standard page.method lines.
        if stripped.startswith("page."):
            step = parse_normal_line(stripped, step_counter)
            step_counter += 1
            steps.append(step)
        
        i += 1
    
    return steps

def find_best_replacement(line: str):
    """Find the best VARIABLE_LABELS replacement based on keywords present in the full line."""
    lower_line = line.lower()
    for label, keywords in VARIABLE_LABELS.items():
        for keyword in keywords:
#            if keyword in lower_line:  # If any keyword appears in the line
            if re.search(rf"\b{re.escape(keyword)}\b", lower_line):
                return label  # Suggest the corresponding label
    return None  # No match found

def get_user_choice(argument, suggested_replacement):
    """Refined user interaction for selecting replacements."""
    print(f"Choose variable replacement for \"{argument}\":")

    # Ensure suggested replacement is not duplicated
    options = [label for label in VARIABLE_LABELS.keys()]
    
    for idx, option in enumerate(options, start=1):
        postfix = " (suggested)" if option == suggested_replacement else ""
        print(f" {idx}) {option}{postfix}")

    while True:
        try:
            # Modify input prompt based on whether suggested_replacement exists
            if suggested_replacement:
                prompt = f"\rYour choice [Press Enter for '{suggested_replacement}', CTRL-C to skip]: "
            else:
                prompt = "\rYour choice [CTRL-C to skip]: "
            sys.stdout.write(prompt)
            sys.stdout.flush()
            choice = input().strip()
            if suggested_replacement and choice == "":  # Enter confirms suggested replacement
                return suggested_replacement
            elif choice in map(str, range(1, len(options) + 1)):  # Valid numbered choice
                return options[int(choice) - 1]
            sys.stdout.write("\033[F")  # Move up one line
            sys.stdout.write("\033[K")  # Clear the entire line
            sys.stdout.flush()
        except KeyboardInterrupt:  # CTRL-C keeps the line unchanged
            print("\nSkipping modification.")
            return argument

def process_fill_methods(filename: str):
    """Process `.fill(...)` lines, suggest full-line based replacements, and update the file content."""
    if not os.path.exists(filename):
        logger.error(f"Error: File '{filename}' does not exist.")
        return
    
    try:
        with open(filename, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except Exception as e:
        logger.error(f"Error while reading the file: {e}")
        return
    
    modified_lines = []

    # Define regex pattern inside the function
    fill_pattern = re.compile(r'\.fill\s*\(\s*(["\'])([^"\']+)\1\s*\)')

    for line in lines:
        modified_line = line
        match = fill_pattern.search(line)  # Search for `.fill(...)` in the line

        if match:
            argument = match.group(2)  # First argument inside `.fill(...)`
            suggested_replacement = find_best_replacement(line)

            print(f"\nFound security critical line: {line.strip()}")  # Display full line once
            replacement = get_user_choice(argument, suggested_replacement)

            # Replace only the `.fill(...)` argument in the line
            modified_line = modified_line.replace(f'"{argument}"', f'"{replacement}"').replace(f"'{argument}'", f"'{replacement}'")

        modified_lines.append(modified_line)

    # Write back to file with error handling
    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.writelines(modified_lines)
        logger.info(f"Updated file '{filename}' successfully.")
    except Exception as e:
        logger.error(f"Error while saving the file: {e}")

def playwright_python_to_yaml(service_name: str):
    """ Translates Playwright Python codegen code to a BillCollector recipe yaml."""

    code_file = os.path.join(RECIPES_PLAYWRIGHT_CODE_DIR, f"{service_name}.py")
    if not os.path.exists(code_file):
        logger.error(f"Error: Code file '{code_file}' does not exist.")
        sys.exit(1)

    output_file = f"{RECIPES_PLAYWRIGHT_PREFIX}{service_name}.yaml" 
    output_file = os.path.join(RECIPES_PLAYWRIGHT_DIR, output_file)

    with open(code_file, "r", encoding="utf-8") as f:
        content = f.read()

    steps = parse_playwright_script(content)

    output_data = {
        "$schema": RECIPES_PLAYWRIGHT_SCHEMA_FILE,
        "services": [
            {
                "serviceName": service_name,
                "description": "",
                "steps": steps
            }
        ]
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, sort_keys=False, allow_unicode=True, Dumper=CustomDumper)
    logger.info(f"Recipe has been saved in '{output_file}'.")

def playwright_codegen(url: str, service_name: str):
    """ Generates Playwright Python code for the given URL and saves it to the specified output file."""

    if not os.path.exists(RECIPES_PLAYWRIGHT_CODE_DIR):
        os.makedirs(RECIPES_PLAYWRIGHT_CODE_DIR)
    code_file = os.path.join(RECIPES_PLAYWRIGHT_CODE_DIR, f"{service_name}.py")

    # Run Playwright Codegen with -o flag to directly save output
    subprocess.run(["playwright", 
                    "codegen", url, 
                    "--target=python", 
                    "-o", code_file,
                    ])
    
    # Suggest replacements for potential security discolosures in fill() methods
    process_fill_methods(code_file)
    return True

if __name__ == "__main__":
    sys.stdout = sys.__stdout__
    setup_logging()

    if sys.gettrace():
        # Debugging
        logger.info("Executed in debugger. Debug mode enabled.")
        #url = "https://www.freenet-mobilfunk.de/login/"
        service = "kabeldeutschland"
        #playwright_codegen(url, service)
        playwright_python_to_yaml(service)

    else:
        parser = argparse.ArgumentParser(description="Generates Python code from a web session and translates it to a BillCollector YAML recipe.")
                
        parser.add_argument("-g", action="store_true", help="Generate Playwright Python code from a URL.")
        parser.add_argument("-t", action="store_true", help="Translate Playwright Python code to a BillCollector YAML recipe.")
        parser.add_argument("-u", "--url", type=str, help="URL to generate Playwright Python code from.")
        parser.add_argument("-s", "--service", type=str, help="Service name for the code file and the recipe.")
        
        if len(sys.argv) == 1:
            parser.print_help()
            sys.exit(1)
        args = parser.parse_args()

        if args.g and not (args.url and args.service):
            logger.error("Error: -g requires both --url and --service arguments.")
            sys.exit(1)
        if args.t and not (args.service):
            logger.error("Error: -t requires --service argument.")
            sys.exit(1)
        if args.g and (args.url and args.service):
            playwright_codegen(args.url, args.service.lower())
        if args.t and (args.service):
            playwright_python_to_yaml(args.service.lower())
