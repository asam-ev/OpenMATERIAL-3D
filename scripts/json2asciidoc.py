import os
import json
import re
import copy
import argparse
from typing import List, Dict


def format_main_headline(file_name: str) -> str:
    """
    Convert a file name to a title-style headline for the AsciiDoc.

    Args:
        file_name (str): The base name of the JSON schema file.

    Returns:
        str: The formatted headline.
    """
    file_name = file_name.replace('_', ' ')  # Replace underscores with spaces
    file_name = file_name.replace('-', ' ')  # Replace hyphens with spaces
    return file_name.capitalize()  # Capitalize the first letter


def escape_special_chars(pattern: str) -> str:
    """
    Escape special characters in the pattern string for AsciiDoc compatibility.

    Args:
        pattern (str): The pattern string to be escaped.

    Returns:
        str: The escaped pattern string.
    """
    return pattern.replace("\\", "\\\\")  # Escape backslashes


def generate_asciidoc_array_of_arrays(items: List[Dict], description: str, required: bool) -> str:
    """
    Generate AsciiDoc content for an array of arrays, listing each item as a column.

    Args:
        items (list[dict]): The list of item schemas in the array.
        description (str): The description of the array.
        required (bool): True if the field is a required property.

    Returns:
        str: The generated AsciiDoc content describing the columns.
    """
    content = ""
    if description:
        content += f"{description}\n"

    content += "\nColumns of the table:\n\n"

    for idx, item in enumerate(items, start=1):
        item_description = item.get('description', 'No description')
        content += f"- Column {idx}: {item_description}\n"

    return content


def generate_asciidoc_array_of_objects(array_data: Dict, required: bool, level: int) -> str:
    """
    Generate AsciiDoc content for arrays whose items are objects.

    The array itself is documented first (description, type, required),
    then item object fields are rendered as nested subsections one level
    deeper than the overlying array section.

    Args:
        array_data (dict): The schema fragment of the array field.
        required (bool): True if the array field is required.
        level (int): The heading level of the array field.

    Returns:
        str: The generated AsciiDoc content for the array and its object item fields.
    """
    content = f"{array_data.get('description', '')}\n"

    if "type" in array_data:
        property_type = escape_special_chars(array_data['type'])
        content += f"\n*Type:* `+{property_type}+` +"

    content += f"\n*Required:* {'Yes' if required else 'No'}\n\n"

    items = array_data.get('items', {})
    item_properties = items.get('properties', {}) if isinstance(items, dict) else {}
    item_required_fields = items.get('required', []) if isinstance(items, dict) else []

    if item_properties:
        content += generate_asciidoc_properties(item_properties, item_required_fields, level + 1)
    else:
        content += "No fields defined\n"

    return content


def generate_asciidoc_properties(properties: Dict, required_fields: List[str], level: int = 2) -> str:
    """
    Recursively generate AsciiDoc content for a dictionary of properties.

    Args:
        properties (dict): The dictionary of properties from the JSON schema.
        required_fields (list): The list of required fields.
        level (int): The current heading level in the AsciiDoc file. Defaults to 2.

    Returns:
        str: The generated AsciiDoc content for the properties.
    """
    asciidoc_content = ""

    for prop_name, prop_data in properties.items():
        heading_prefix = "=" * level  # Create heading based on level
        asciidoc_content += f"{heading_prefix} {prop_name}\n"

        if (
            prop_data.get('type') == "array"
            and isinstance(prop_data.get('items'), dict)
            and prop_data['items'].get('type') == 'object'
        ):
            asciidoc_content += generate_asciidoc_array_of_objects(prop_data, prop_name in required_fields, level)
            asciidoc_content += "\n"
            continue

        asciidoc_content += f"{prop_data.get('description', '')}\n"

        # Add data type of the property
        if "type" in prop_data:
            property_type = escape_special_chars(prop_data['type'])
            asciidoc_content += f"\n*Type:* `+{property_type}+` +"

        # Add enum options
        if "enum" in prop_data:
            asciidoc_content += f"\n*Enum:* `+{prop_data['enum']}+` +"

        # Add pattern inline and handle escaping of backslashes and curly braces
        if "pattern" in prop_data:
            pattern = escape_special_chars(prop_data['pattern'])
            asciidoc_content += f"\n*Pattern:* `+{pattern}+` +"

        # Add minimum and maximum values
        if "minimum" in prop_data:
            asciidoc_content += f"\n*Minimum value:* `+{prop_data['minimum']}+` +"
        if "maximum" in prop_data:
            asciidoc_content += f"\n*Maximum value:* `+{prop_data['maximum']}+` +"

        # Add required status
        asciidoc_content += f"\n*Required:* {'Yes' if prop_name in required_fields else 'No'}\n\n"

        # Handle array types and generate description for array of arrays
        if prop_data.get('type') == "array":
            if isinstance(prop_data['items'], dict) and 'items' in prop_data['items']:
                # Generate list for array of arrays
                asciidoc_content += generate_asciidoc_array_of_arrays(
                    prop_data['items']['items'], prop_data['items'].get('description', ''), prop_name in required_fields
                ) + "\n"
            elif isinstance(prop_data['items'], list):
                # If it's a list of items, generate columns description directly
                asciidoc_content += generate_asciidoc_array_of_arrays(
                    prop_data['items'], prop_data.get('description', ''), prop_name in required_fields
                ) + "\n"
            else:
                # Simple array, include the description of the array
                # Add enum options
                if "enum" in prop_data['items']:
                    asciidoc_content += f"\n*Items enum:* `+{prop_data['items'].get('enum', '')}+` +"
                asciidoc_content += f"\n{prop_data['items'].get('description', '')}\n"

        asciidoc_content += "\n"

        # If there are nested properties, recursively generate content for them
        if "properties" in prop_data:
            nested_required_fields = prop_data.get('required', [])
            asciidoc_content += generate_asciidoc_properties(
                prop_data['properties'], nested_required_fields, level + 1
            )

    return asciidoc_content


def generate_asciidoc_main_field(field_name: str, schema: Dict, is_required: bool, required_fields: List[str]) -> str:
    """
    Generate AsciiDoc content for the specified field based on the JSON schema.

    Args:
        field_name (str): The name of the field to generate documentation for.
        schema (dict): The JSON schema dictionary.
        is_required (bool): True if the field is required
        required_fields (list): List of required fields for the specified field.

    Returns:
        str: The generated AsciiDoc content.
    """
    asciidoc_content = f"== {field_name}\n\n"
    field_data = schema['properties'][field_name]

    if (
        field_data.get('type') == 'array'
        and isinstance(field_data.get('items'), dict)
        and field_data['items'].get('type') == 'object'
    ):
        asciidoc_content += generate_asciidoc_array_of_objects(field_data, is_required, level=2)
        return asciidoc_content

    asciidoc_content += field_data.get("description", "") + "\n\n"

    if "type" in field_data:
        property_type = escape_special_chars(field_data['type'])
        asciidoc_content += f"\n*Type:* `+{property_type}+` +"
    if "pattern" in field_data:
        pattern = escape_special_chars(field_data['pattern'])
        asciidoc_content += f"\n*Pattern:* `+{pattern}+` +"
    asciidoc_content += f"\n*Required:* {'Yes' if is_required else 'No'}\n\n"

    # Generate the content for the properties, recursively handling nested properties
    if 'properties' in field_data:
        asciidoc_content += generate_asciidoc_properties(field_data['properties'], required_fields, level=3)
    elif field_data.get('type') == 'array':
        if 'items' in field_data and isinstance(field_data['items'], dict) and 'items' in field_data['items']:
            asciidoc_content += generate_asciidoc_array_of_arrays(
                field_data['items']['items'], field_data['items'].get('description', ''), field_name in required_fields
            ) + "\n"
        elif isinstance(field_data['items'], list):
            asciidoc_content += generate_asciidoc_array_of_arrays(
                field_data['items'], field_data.get('description', ''), field_name in required_fields
            ) + "\n"
        else:
            asciidoc_content += f"\n{field_data['items'].get('description', 'No description')}\n"

    return asciidoc_content


def generate_heading_id(text: str) -> str:
    """
    Approximate the auto-generated AsciiDoc section ID for a heading with the given text.

    Args:
        text (str): The heading text, i.e. the property name.

    Returns:
        str: The approximated section ID, including the leading underscore.
    """
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_').lower()
    return f"_{slug}"


def build_hierarchy_tree(schema: Dict) -> List[Dict]:
    """
    Build a tree mirroring the section hierarchy that will be generated for the schema,
    so it can be rendered as an overview hierarchy diagram.

    Traverses the schema properties in the same order and with the same rules used by
    generate_asciidoc_main_field/generate_asciidoc_properties, so that section IDs assigned
    here line up with the IDs AsciiDoc will auto-generate for the actual headings.

    Args:
        schema (dict): The (reference-resolved) JSON schema.

    Returns:
        list[dict]: The top-level nodes of the hierarchy tree. Each node has the keys
                     'name', 'required', 'id', and 'children'.
    """
    id_counts: Dict[str, int] = {}

    def next_id(name: str) -> str:
        base = generate_heading_id(name)
        count = id_counts.get(base, 0) + 1
        id_counts[base] = count
        return base if count == 1 else f"{base}_{count}"

    def build_node(name: str, field_data: Dict, required: bool) -> Dict:
        node = {"name": name, "required": required, "id": next_id(name), "children": []}

        if (
            field_data.get("type") == "array"
            and isinstance(field_data.get("items"), dict)
            and field_data["items"].get("type") == "object"
        ):
            item_properties = field_data["items"].get("properties", {})
            item_required_fields = field_data["items"].get("required", [])
            for child_name, child_data in item_properties.items():
                node["children"].append(build_node(child_name, child_data, child_name in item_required_fields))
        elif "properties" in field_data:
            nested_required_fields = field_data.get("required", [])
            for child_name, child_data in field_data["properties"].items():
                node["children"].append(build_node(child_name, child_data, child_name in nested_required_fields))

        return node

    top_required_fields = schema.get("required", [])
    return [
        build_node(name, field_data, name in top_required_fields)
        for name, field_data in schema["properties"].items()
    ]


def render_hierarchy_diagram(headline: str, tree: List[Dict]) -> str:
    """
    Render a hierarchy tree as a PlantUML legend diagram, similar to the vehicle structure
    overview diagram, preceded by an explanatory sentence. Required fields are marked with "(R)".

    Args:
        headline (str): The label for the virtual root node representing the whole schema.
        tree (list[dict]): The hierarchy tree as returned by build_hierarchy_tree.

    Returns:
        str: The AsciiDoc content for the overview section, including the heading.
    """
    lines = [headline]

    def render_node(node: Dict, level: int) -> None:
        entry = f"[[#{node['id']} {node['name']}]]"
        if node["required"]:
            entry += " (R)"
        indent = "  " * (level - 1)
        lines.append(f"{indent}|_ {entry}")
        for child in node["children"]:
            render_node(child, level + 1)

    for node in tree:
        render_node(node, 1)

    diagram_body = "\n".join(lines)

    description = (
        "This diagram shows the hierarchy of the fields defined in this schema. "
        "Fields marked with `\\(R)` are required. "
        "A field can be optional while some of its children are required. "
        "In that case, the required children only have to be filled in if the optional parent field is present.\n\n"
    )

    return (
        "== Overview\n\n"
        f"{description}"
        "[plantuml]\n"
        "----\n"
        "legend\n"
        f"{diagram_body}\n"
        "end legend\n"
        "----\n\n"
    )


def resolve_references(definitions, schema):
    """
        Resolve JSON Schema references in the provided schema using the given definitions.

        This function recursively traverses the input schema, replacing `$ref` fields with their corresponding
        definitions from the `definitions` dictionary. It supports nested objects and arrays, ensuring that
        all references within the schema are resolved. The function also preserves additional fields in objects
        containing `$ref`.

        Args:
            definitions (dict): A dictionary containing schema definitions, where keys are the definition names
                                and values are the corresponding schema fragments.
            schema (dict or list): The JSON schema to process. This can be an object, an array, or any other valid
                                   JSON structure.

        Returns:
            dict or list: The schema with all `$ref` references resolved.

        Note:
            - If a `$ref` cannot be resolved (e.g., the referenced key is missing from `definitions`), the function
              leaves the `$ref` field untouched.
            - Circular references are not handled and may cause infinite recursion.
    """
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref.startswith("#/definitions/"):
                definition_key = ref.split("/")[-1]
                if definition_key in definitions:
                    resolved_def = copy.deepcopy(definitions[definition_key])
                    # Include other fields in the original object
                    schema.pop("$ref")
                    schema.update(resolved_def)
        else:
            # Recursively resolve other fields
            for key, value in schema.items():
                schema[key] = resolve_references(definitions, value)
    elif isinstance(schema, list):
        schema = [resolve_references(definitions, item) for item in schema]
    return schema


def generate_asciidoc_file(json_schema_path: str, output_path: str):
    """
    Generate AsciiDoc file for the given JSON schema.

    Args:
        json_schema_path (str): Path to the json schema.
        output_path:  (str): Path to write the ASCIIdoc file to.
    """
    with open(json_schema_path, 'r') as file:
        schema = json.load(file)

    definitions = schema.get("definitions", {})
    schema = resolve_references(definitions, schema)

    base_filename = os.path.basename(json_schema_path).replace('_', '-')
    headline = format_main_headline(os.path.splitext(base_filename)[0])
    headline = headline.replace("reflcoeff", "reflection coefficient")     # This is an exception because of the abbreviation of reflection coefficient in the schema file name
    asciidoc_content = f"= {headline}\n\n"

    hierarchy_tree = build_hierarchy_tree(schema)
    asciidoc_content += render_hierarchy_diagram(headline, hierarchy_tree)

    for field in schema['properties']:
        is_required = field in schema.get('required', [])
        required_fields = schema['properties'][field].get('required', [])
        asciidoc_content += generate_asciidoc_main_field(field, schema, is_required, required_fields)

    output_filename = f"{os.path.splitext(base_filename)[0]}.adoc"
    output_filename = output_filename.replace("reflCoeff", "reflection-coefficient")  # This is an exception because of the abbreviation of reflection coefficient in the schema file name
    output_file = os.path.join(output_path, output_filename)

    with open(output_file, 'w') as file:
        file.write(asciidoc_content)

    print(f"AsciiDoc generated successfully! Output saved to {output_file}")


def main() -> None:
    """
    Handle command-line arguments, process the JSON schema, and generate the AsciiDoc documentation.
    """
    parser = argparse.ArgumentParser(
        description="Generate AsciiDoc documentation for a JSON schema field or the entire schema.")
    parser.add_argument('json_schema_path', type=str, help="Path to the JSON schema file.")
    args = parser.parse_args()

    generate_asciidoc_file(args.json_schema_path, ".")


if __name__ == "__main__":
    main()
