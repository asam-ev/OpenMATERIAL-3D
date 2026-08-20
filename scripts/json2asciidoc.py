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


def format_literal(value) -> str:
    """
    Render a schema value as inline monospace text without AsciiDoc substitutions.

    A passthrough span is required because schema values contain characters that AsciiDoc would
    otherwise interpret, most notably backslashes and curly braces in regular expressions. Two
    plus signs are used as the delimiter so that patterns containing a single plus sign, such as
    "^\\d+$", do not terminate the span early.

    Args:
        value: The value to render.

    Returns:
        str: The value wrapped in an inline monospace passthrough span.
    """
    return f"`++{value}++`"


def format_type(type_value) -> str:
    """
    Render the value of a "type" keyword, which may be a single type or a list of types.

    Args:
        type_value (str or list): The value of the "type" keyword.

    Returns:
        str: A human-readable type, for example "number" or "number or null".
    """
    if isinstance(type_value, list):
        return " or ".join(str(entry) for entry in type_value)
    return str(type_value)


def format_number(value) -> str:
    """
    Render a numeric bound the way it is written in the schema.

    Args:
        value: The numeric value of a bound.

    Returns:
        str: The formatted number, for example "1e-09" or "0.01716".
    """
    return repr(value) if isinstance(value, float) else str(value)


def format_range(fragment: Dict) -> str:
    """
    Render the numeric bounds of a schema fragment as a mathematical interval.

    Square brackets denote inclusive bounds and reversed square brackets denote exclusive bounds,
    following the notation already used throughout {THIS_STANDARD}, for example "]0, inf[".

    Args:
        fragment (dict): The schema fragment to read the bounds from.

    Returns:
        str: The interval, or an empty string if the fragment declares no bounds.
    """
    has_min = "minimum" in fragment or "exclusiveMinimum" in fragment
    has_max = "maximum" in fragment or "exclusiveMaximum" in fragment

    if not has_min and not has_max:
        return ""

    if "exclusiveMinimum" in fragment:
        lower = f"]{format_number(fragment['exclusiveMinimum'])}"
    elif "minimum" in fragment:
        lower = f"[{format_number(fragment['minimum'])}"
    else:
        lower = "]-inf"

    if "exclusiveMaximum" in fragment:
        upper = f"{format_number(fragment['exclusiveMaximum'])}["
    elif "maximum" in fragment:
        upper = f"{format_number(fragment['maximum'])}]"
    else:
        upper = "inf["

    return f"{lower}, {upper}"


def format_item_count(fragment: Dict) -> str:
    """
    Render the "minItems" and "maxItems" keywords of a schema fragment as a readable constraint.

    Args:
        fragment (dict): The schema fragment to read the item count from.

    Returns:
        str: The item count constraint, or an empty string if the fragment declares none.
    """
    min_items = fragment.get("minItems")
    max_items = fragment.get("maxItems")

    if min_items is None and max_items is None:
        return ""
    if min_items is not None and min_items == max_items:
        return f"exactly {min_items}"
    if max_items is None:
        return f"at least {min_items}"
    if min_items is None:
        return f"at most {max_items}"
    return f"{min_items} to {max_items}"


def is_simple_array(fragment: Dict) -> bool:
    """
    Determine whether a schema fragment is an array whose items are scalars.

    Arrays of objects and arrays of arrays are documented as nested sections or as tables, so their
    item schemas must not be summarized as inline attributes.

    Args:
        fragment (dict): The schema fragment to inspect.

    Returns:
        bool: True if the fragment is an array of scalar items.
    """
    items = fragment.get("items")
    if fragment.get("type") != "array" or not isinstance(items, dict):
        return False
    return "properties" not in items and "items" not in items


def render_constraints(fragment: Dict, required: bool = None) -> str:
    """
    Render every constraint a schema fragment declares as a block of inline AsciiDoc attributes.

    This is the single place where schema keywords are turned into documentation, so that all
    constraints are reported consistently no matter whether the fragment is a top-level field, a
    nested property, or an array. Scalar array items are summarized with "Item" attributes, because
    they get no section of their own.

    Args:
        fragment (dict): The schema fragment to document.
        required (bool): True if the fragment is a required property, False if it is optional, or
                         None to omit the required attribute entirely.

    Returns:
        str: The generated AsciiDoc attribute block.
    """
    content = ""

    if "type" in fragment:
        content += f"\n*Type:* {format_literal(format_type(fragment['type']))} +"
    if "format" in fragment:
        content += f"\n*Format:* {format_literal(fragment['format'])} +"
    if "enum" in fragment:
        content += f"\n*Enum:* {format_literal(format_enum(fragment['enum']))} +"
    if "pattern" in fragment:
        content += f"\n*Pattern:* {format_literal(fragment['pattern'])} +"

    value_range = format_range(fragment)
    if value_range:
        content += f"\n*Range:* {format_literal(value_range)} +"

    item_count = format_item_count(fragment)
    if item_count:
        content += f"\n*Item count:* {format_literal(item_count)} +"

    if fragment.get("uniqueItems"):
        content += "\n*Unique items:* Yes +"

    if is_simple_array(fragment):
        items = fragment["items"]
        if "type" in items:
            content += f"\n*Item type:* {format_literal(format_type(items['type']))} +"
        if "format" in items:
            content += f"\n*Item format:* {format_literal(items['format'])} +"
        if "enum" in items:
            content += f"\n*Item enum:* {format_literal(format_enum(items['enum']))} +"
        if "pattern" in items:
            content += f"\n*Item pattern:* {format_literal(items['pattern'])} +"
        item_range = format_range(items)
        if item_range:
            content += f"\n*Item range:* {format_literal(item_range)} +"

    if required is None:
        # Drop the trailing hard line break of the last attribute.
        return content[:-2] + "\n\n" if content.endswith(" +") else content
    content += f"\n*Required:* {'Yes' if required else 'No'}\n\n"

    return content


def format_enum(values: List) -> str:
    """
    Render the value of an "enum" keyword as a readable list.

    Args:
        values (list): The allowed values.

    Returns:
        str: The values, quoted and comma-separated.
    """
    return ", ".join(f"'{value}'" if isinstance(value, str) else str(value) for value in values)


def render_conditional_rules(fragment: Dict) -> str:
    """
    Render the conditional constraints of a schema fragment as normative sentences.

    JSON Schema expresses co-dependencies with "dependencies" and mutual exclusivity with
    "oneOf"/"not", neither of which is self-explanatory to a reader of the specification. Only the
    shapes actually used by {THIS_STANDARD} are recognized; anything else is reported as an
    unhandled keyword by audit_keywords so that it cannot be dropped silently.

    Args:
        fragment (dict): The schema fragment to inspect.

    Returns:
        str: The generated AsciiDoc content, or an empty string if there are no such constraints.
    """
    sentences = []

    for prop_name, dependencies in fragment.get("dependencies", {}).items():
        if isinstance(dependencies, list):
            required = ", ".join(f"'{dependency}'" for dependency in dependencies)
            sentences.append(f"If '{prop_name}' is set, {required} shall also be set.")

    exclusive = describe_mutual_exclusion(fragment.get("oneOf"))
    if exclusive:
        sentences.append(exclusive)

    if not sentences:
        return ""

    return "\n".join(f"NOTE: {sentence}\n" for sentence in sentences) + "\n"


def describe_mutual_exclusion(one_of) -> str:
    """
    Recognize a "oneOf" construct that makes a set of properties mutually exclusive.

    The construct consists of one branch per property, each requiring that property and forbidding
    the others, plus an optional final branch forbidding all of them, which permits omitting them
    all.

    Args:
        one_of (list): The value of the "oneOf" keyword, or None.

    Returns:
        str: A sentence describing the constraint, or an empty string if the construct is not of
             this shape.
    """
    if not isinstance(one_of, list) or len(one_of) < 2:
        return ""

    names = []
    allows_none = False
    for branch in one_of:
        if not isinstance(branch, dict):
            return ""
        required = branch.get("required", [])
        if len(required) == 1:
            names.append(required[0])
        elif not required and "not" in branch:
            allows_none = True
        else:
            return ""

    if len(names) < 2 or len(one_of) != len(names) + (1 if allows_none else 0):
        return ""

    quoted = ", ".join(f"'{name}'" for name in names[:-1]) + f" and '{names[-1]}'"
    sentence = f"Only one of {quoted} shall be set."
    if allows_none:
        sentence += " All of them may be omitted."
    return sentence


def generate_asciidoc_table(container: Dict, description: str) -> str:
    """
    Generate an AsciiDoc table documenting the columns of a fixed-length data array.

    Look-up tables are declared as arrays of fixed-length arrays, where the position of a value
    determines its meaning. Each position is documented as a table row so that its type and its
    bounds are visible next to its description, instead of being dropped.

    Args:
        container (dict): The schema fragment whose "items" keyword holds the list of column
                          schemas, and which may declare the row length via "minItems"/"maxItems".
        description (str): The description of the array.

    Returns:
        str: The generated AsciiDoc content describing the columns.
    """
    columns = container.get("items", [])

    content = ""
    if description:
        content += f"{description}\n"

    item_count = format_item_count(container)
    if item_count:
        content += f"\n*Column count:* {format_literal(item_count)}\n"

    content += "\nColumns of the table:\n\n"
    content += '[cols="1,2,2,6",options="header"]\n|===\n'
    content += "| Column | Type | Constraints | Description\n\n"

    for idx, column in enumerate(columns, start=1):
        column_type = format_type(column["type"]) if "type" in column else ""
        content += (
            f"| {idx} | {escape_cell(column_type)} | {escape_cell(format_column_constraints(column))} "
            f"| {escape_cell(str(column.get('description', '')))}\n"
        )

    content += "|===\n"

    return content


def escape_cell(text: str) -> str:
    """
    Escape the content of an AsciiDoc table cell.

    The vertical bar separates cells, so a literal one, as contained in the alternation of a
    regular expression, would split the row into additional cells.

    Args:
        text (str): The cell content.

    Returns:
        str: The escaped cell content.
    """
    return text.replace("|", "\\|")


def format_column_constraints(column: Dict) -> str:
    """
    Render every constraint of a single table column into one table cell.

    Columns get no section of their own, so all of their constraints have to fit into a single
    cell. Keeping this in one place makes sure a constraint is not lost just because the table has
    no dedicated column for it.

    Args:
        column (dict): The schema fragment of the column.

    Returns:
        str: The constraints, separated by AsciiDoc hard line breaks.
    """
    constraints = []

    value_range = format_range(column)
    if value_range:
        constraints.append(format_literal(value_range))
    if "enum" in column:
        constraints.append(format_literal(format_enum(column["enum"])))
    if "pattern" in column:
        constraints.append(format_literal(column["pattern"]))
    if "format" in column:
        constraints.append(format_literal(column["format"]))

    return " +\n".join(constraints)


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
    content += render_constraints(array_data, required)

    items = array_data.get('items', {})
    item_properties = items.get('properties', {}) if isinstance(items, dict) else {}
    item_required_fields = items.get('required', []) if isinstance(items, dict) else []

    if isinstance(items, dict):
        content += render_conditional_rules(items)

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
        asciidoc_content += render_constraints(prop_data, prop_name in required_fields)
        asciidoc_content += render_conditional_rules(prop_data)

        # Handle array types and generate the column table for arrays of arrays
        if prop_data.get('type') == "array":
            items = prop_data.get('items')
            if isinstance(items, dict) and isinstance(items.get('items'), list):
                # Array of fixed-length arrays, documented as a table of columns
                asciidoc_content += generate_asciidoc_table(items, items.get('description', '')) + "\n"
            elif isinstance(items, list):
                # The array itself is of fixed length, documented as a table of columns
                asciidoc_content += generate_asciidoc_table(prop_data, '') + "\n"
            elif isinstance(items, dict):
                # Simple array, include the description of the items. The item constraints are
                # already reported by render_constraints.
                item_description = items.get('description', '')
                if item_description:
                    asciidoc_content += f"\n{item_description}\n"

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
    asciidoc_content += render_constraints(field_data, is_required)
    asciidoc_content += render_conditional_rules(field_data)

    # Generate the content for the properties, recursively handling nested properties
    if 'properties' in field_data:
        asciidoc_content += generate_asciidoc_properties(field_data['properties'], required_fields, level=3)
    elif field_data.get('type') == 'array':
        items = field_data.get('items')
        if isinstance(items, dict) and isinstance(items.get('items'), list):
            asciidoc_content += generate_asciidoc_table(items, items.get('description', '')) + "\n"
        elif isinstance(items, list):
            asciidoc_content += generate_asciidoc_table(field_data, '') + "\n"
        elif isinstance(items, dict):
            item_description = items.get('description', '')
            if item_description:
                asciidoc_content += f"\n{item_description}\n"

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


def compute_page_link_prefix(output_path: str) -> str:
    """
    Compute the relative link prefix pointing from the rendered diagram image (which lives in
    the shared content/_images directory) to the HTML page that will be generated for this file.

    PlantUML diagrams are rendered to standalone SVG images, so links embedded in them are
    resolved relative to the SVG file itself, not the page it is displayed on. This means
    fragment-only links (e.g. "#_metadata") do not work and the link must instead point back at
    the compiled page explicitly, mirroring the convention used in vehicle-structure.adoc.

    Args:
        output_path (str): The directory the AsciiDoc file is written to.

    Returns:
        str: The relative path prefix, for example "../07_geometry", to prepend to the page
             filename and anchor.
    """
    parts = os.path.normpath(output_path).split(os.sep)
    if "content" in parts:
        page_dir = "/".join(parts[parts.index("content") + 1:])
    else:
        page_dir = ""
    return f"../{page_dir}" if page_dir else ".."


def render_hierarchy_diagram(headline: str, tree: List[Dict], page_url: str, schema_filename: str) -> str:
    """
    Render a hierarchy tree as a PlantUML legend diagram, similar to the vehicle structure
    overview diagram, preceded by an explanatory sentence. Required fields are marked with "(R)".

    Args:
        headline (str): The label for the virtual root node representing the whole schema.
        tree (list[dict]): The hierarchy tree as returned by build_hierarchy_tree.
        page_url (str): The relative URL of the HTML page this diagram will be embedded in,
                         used as the base for the section anchor links (e.g.
                         "../07_geometry/asset-schema.html").
        schema_filename (str): The base file name of the JSON schema (e.g. "asset_schema.json"),
                                used to link to the actual file in the OpenMATERIAL-3D repository.

    Returns:
        str: The AsciiDoc content for the overview section, including the heading.
    """
    lines = [headline]

    def render_node(node: Dict, level: int) -> None:
        entry = f"[[{page_url}#{node['id']} {node['name']}]]"
        if node["required"]:
            entry += " (R)"
        indent = "  " * (level - 1)
        lines.append(f"{indent}|_ {entry}")
        for child in node["children"]:
            render_node(child, level + 1)

    for node in tree:
        render_node(node, 1)

    diagram_body = "\n".join(lines)

    schema_url = f"https://github.com/asam-ev/OpenMATERIAL-3D/blob/main/schemas/{schema_filename}"
    description = (
        "This is the documentation about the JSON schema file. "
        f"The actual file is located in the ASAM OpenMATERIAL 3D link:{schema_url}[GitHub repository].\n\n"
        "The following diagram shows the hierarchy of the fields defined in this schema. "
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


def resolve_references(definitions, schema, _resolving=None):
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
    if _resolving is None:
        _resolving = set()

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref.startswith("#/definitions/"):
                definition_key = ref.split("/")[-1]
                if definition_key in definitions and definition_key not in _resolving:
                    resolved_def = copy.deepcopy(definitions[definition_key])
                    # Keep the fields of the referencing object, which take precedence over the
                    # ones of the definition, so that a local description is not overwritten.
                    local_fields = {key: value for key, value in schema.items() if key != "$ref"}
                    schema.clear()
                    schema.update(resolved_def)
                    schema.update(local_fields)
                    # Resolve references nested inside the definition as well, guarding against
                    # definitions that refer back to themselves.
                    _resolving = _resolving | {definition_key}
        for key, value in schema.items():
            schema[key] = resolve_references(definitions, value, _resolving)
    elif isinstance(schema, list):
        schema = [resolve_references(definitions, item, _resolving) for item in schema]
    return schema


# Every JSON Schema keyword that this generator turns into documentation. Any other keyword found
# in a schema is reported by audit_keywords, so that a constraint can never be dropped silently.
HANDLED_KEYWORDS = {
    "$schema", "$ref", "definitions", "title", "description", "type", "properties", "items",
    "required", "enum", "pattern", "format", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minItems", "maxItems", "uniqueItems", "dependencies", "oneOf", "not",
    "anyOf",
}


def audit_keywords(schema, path: str = "$") -> List[str]:
    """
    Collect every JSON Schema keyword that this generator does not document.

    The generator is the only rendering of the schemas that readers of the specification see, so a
    keyword it does not know about is a normative requirement missing from the specification. This
    walk reports those keywords instead of letting them disappear.

    Only schema positions are visited, so property names are never mistaken for keywords.

    Args:
        schema: The schema fragment to audit.
        path (str): The JSON path of the fragment, used to report where a keyword was found.

    Returns:
        list[str]: One "path: keyword" entry per unhandled keyword occurrence.
    """
    findings: List[str] = []

    if not isinstance(schema, dict):
        return findings

    for keyword, value in schema.items():
        if keyword not in HANDLED_KEYWORDS:
            findings.append(f"{path}: {keyword}")

    for keyword in ("properties", "definitions"):
        for name, sub_schema in schema.get(keyword, {}).items():
            findings += audit_keywords(sub_schema, f"{path}.{name}")

    items = schema.get("items")
    if isinstance(items, dict):
        findings += audit_keywords(items, f"{path}[]")
    elif isinstance(items, list):
        for index, sub_schema in enumerate(items):
            findings += audit_keywords(sub_schema, f"{path}[{index}]")

    for keyword in ("oneOf", "anyOf", "allOf"):
        for index, sub_schema in enumerate(schema.get(keyword, [])):
            findings += audit_keywords(sub_schema, f"{path}.{keyword}[{index}]")

    for keyword in ("not", "if", "then", "else"):
        if isinstance(schema.get(keyword), dict):
            findings += audit_keywords(schema[keyword], f"{path}.{keyword}")

    for name, value in schema.get("dependencies", {}).items():
        if isinstance(value, dict):
            findings += audit_keywords(value, f"{path}.dependencies.{name}")

    return findings


def generate_asciidoc_file(json_schema_path: str, output_path: str):
    """
    Generate AsciiDoc file for the given JSON schema.

    Args:
        json_schema_path (str): Path to the json schema.
        output_path:  (str): Path to write the ASCIIdoc file to.
    """
    with open(json_schema_path, 'r') as file:
        schema = json.load(file)

    unhandled_keywords = audit_keywords(schema)

    definitions = schema.get("definitions", {})
    schema = resolve_references(definitions, schema)

    base_filename = os.path.basename(json_schema_path).replace('_', '-')
    headline = format_main_headline(os.path.splitext(base_filename)[0])
    headline = headline.replace("reflcoeff", "reflection coefficient")     # This is an exception because of the abbreviation of reflection coefficient in the schema file name
    asciidoc_content = f"= {headline}\n\n"

    output_filename = f"{os.path.splitext(base_filename)[0]}.adoc"
    output_filename = output_filename.replace("reflCoeff", "reflection-coefficient")  # This is an exception because of the abbreviation of reflection coefficient in the schema file name
    html_filename = f"{os.path.splitext(output_filename)[0]}.html"
    page_url = f"{compute_page_link_prefix(output_path)}/{html_filename}"

    hierarchy_tree = build_hierarchy_tree(schema)
    asciidoc_content += render_hierarchy_diagram(headline, hierarchy_tree, page_url, os.path.basename(json_schema_path))

    for field in schema['properties']:
        is_required = field in schema.get('required', [])
        required_fields = schema['properties'][field].get('required', [])
        asciidoc_content += generate_asciidoc_main_field(field, schema, is_required, required_fields)

    output_file = os.path.join(output_path, output_filename)

    with open(output_file, 'w') as file:
        file.write(asciidoc_content)

    print(f"AsciiDoc generated successfully! Output saved to {output_file}")

    if unhandled_keywords:
        print(
            f"WARNING: {len(unhandled_keywords)} keyword(s) in {os.path.basename(json_schema_path)} "
            "are not documented by this generator and are missing from the specification:"
        )
        for finding in unhandled_keywords:
            print(f"  {finding}")


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
