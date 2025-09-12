import re
from typing import List

def split_into_statements(js_code: str) -> List[str]:
    """
    Split JavaScript code into statements while respecting string boundaries.
    Handles both single and double quotes, and escaped quotes within strings.
    
    Args:
        js_code (str): JavaScript code potentially in a single line
        
    Returns:
        List[str]: List of individual JavaScript statements
    """
    statements = []
    current_statement = []
    pos = 0
    length = len(js_code)
    
    # State tracking
    in_single_quote = False
    in_double_quote = False
    in_template_literal = False
    escape_next = False
    
    while pos < length:
        char = js_code[pos]
        
        # Handle escape sequences
        if escape_next:
            current_statement.append(char)
            escape_next = False
            pos += 1
            continue
            
        if char == '\\':
            current_statement.append(char)
            escape_next = True
            pos += 1
            continue
            
        # Handle string boundaries
        if char == '"' and not in_single_quote and not in_template_literal:
            in_double_quote = not in_double_quote
        elif char == "'" and not in_double_quote and not in_template_literal:
            in_single_quote = not in_single_quote
        elif char == '`' and not in_single_quote and not in_double_quote:
            in_template_literal = not in_template_literal
            
        # Handle semicolons
        if (char == ';' and 
            not in_single_quote and 
            not in_double_quote and 
            not in_template_literal):
            current_statement.append(char)
            statement = ''.join(current_statement).strip()
            if statement:
                statements.append(statement)
            current_statement = []
            pos += 1
            continue
            
        current_statement.append(char)
        pos += 1
    
    # Add the last statement if it exists
    last_statement = ''.join(current_statement).strip()
    if last_statement:
        statements.append(last_statement)
        
    return statements

def get_js(js_code: str) -> dict:
    """
    Extract global variables and their values from JavaScript code.
    
    Args:
        js_code (str): JavaScript code as a string
    
    Returns:
        dict: Dictionary mapping global variable names to their values
    """

    # js_code = re.sub(r'/\*[\s\S]*?\*/', '', js_code)
    # js_code = re.sub(r'//.*$', '', js_code, flags=re.MULTILINE)

    # Split code into statements
    statements = split_into_statements(js_code)
    
    # Dictionary to store global variables and their values
    globals_dict = {}
    
    # variables with low confidence
    low_dict = {}

    # Regular expression patterns for different declaration types
    patterns = [
        # var/let/const declarations
        r'(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*([^;]+)',
        # Direct assignments to window object
        r'window\.([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*([^;]+)',
        # Global this assignments
        r'globalThis\.([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*([^;]+)',
        # Direct global assignments without var/let/const
        r'(?:^|[{;,])([a-zA-Z_$][a-zA-Z0-9_$]*)\s*[=:]\s*([^;,}]+)'
    ]

    class_pattern = r'classList.add\([\'"]([^\'"]+)'
    classes = re.findall(class_pattern, js_code)
    
    def clean_value(value: str) -> str:
        """Clean and normalize the extracted value."""
        value = value.strip()
        # Handle trailing commas
        if value.endswith(','):
            value = value[:-1]
        return value
    
    def parse_js_value(value: str) -> object:
        """Convert JavaScript value strings to Python objects."""
        value = clean_value(value)
        try:
            # Handle boolean values
            if value.lower() == 'true':
                return True
            if value.lower() == 'false':
                return False
            # Handle null
            if value.lower() == 'null':
                return None
            # Handle undefined
            if value.lower() == 'undefined':
                return None
            # Handle strings with quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
            # Handle arrays
            if value.startswith('[') and value.endswith(']'):
                try:
                    # Simple array parsing - doesn't handle nested structures
                    items = value[1:-1].split(',')
                    return [parse_js_value(item) for item in items if item.strip()]
                except:
                    return value
            # Handle objects
            if value.startswith('{') and value.endswith('}'):
                return value  # Return as string, as proper object parsing would be complex
            # If we can't parse it, return as is
            return value
        except:
            return value
    
    # Process each statement
    for statement in statements:
        statement = statement.strip()
        if not statement:
            continue
            
        for pattern in patterns:
            matches = re.finditer(pattern, statement, re.MULTILINE)
            for match in matches:
                var_name = match.group(1)
                value = match.group(2)
                confidence_level = 3
                if len(var_name) <= 3:
                    confidence_level -= 2
                elif len(var_name) <= 5:
                    confidence_level -= 1
                
                if ('var' or 'let' or 'const') in match.group(0).split(var_name)[0]:
                    # Skip if it's inside a function declaration
                    if re.search(r'function\s*\(.*\)\s*{', statement):
                        continue
                        
                    # Skip if it's part of a class declaration
                    if re.search(r'class\s+', statement):
                        continue
                
                if pattern == patterns[3]:
                    if match.group(0).split(var_name)[1].strip().startswith(':'):
                        if var_name.startswith('http') and value.startswith('//'):
                            continue
                        confidence_level -= 1
                        if confidence_level <= 0:
                            continue
                        parsed_value = parse_js_value(value)
                        low_dict[var_name] = parsed_value
                        continue
                    
                # Process the value
                parsed_value = parse_js_value(value)
                globals_dict[var_name] = parsed_value

    return globals_dict, low_dict, classes
