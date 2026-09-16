"""
Macro Execution Module

Handles execution of macro files containing sequences of TV commands.
"""

import logging
import csv
from pathlib import Path
from typing import Dict, Any

from helpers import tvcon


def execute(config: Dict[str, Any], filename: str) -> bool:
    """
    Execute a macro file containing TV commands.
    
    Args:
        config: TV configuration dictionary
        filename: Path to the macro CSV file
        
    Returns:
        True if macro executed successfully, False otherwise
        
    The macro file should be a CSV with columns:
    - key: The command to send (e.g., 'KEY_POWER', 'KEY_VOLUP')
    - wait: Time to wait after command in milliseconds (optional, defaults to 500)
    
    Lines starting with '#' are treated as comments and ignored.
    """
    logger = logging.getLogger(__name__)
    
    macro_path = Path(filename)
    
    if not macro_path.exists():
        logger.error(f'Macro file not found: {filename}')
        return False
    
    if not macro_path.is_file():
        logger.error(f'Path is not a file: {filename}')
        return False
    
    try:
        with open(macro_path, newline='', encoding='utf-8') as macro_file:
            reader = csv.DictReader(macro_file, fieldnames=('key', 'wait'))

            line_number = 0
            for line in reader:
                line_number += 1
                key = line['key'].strip() if line['key'] else ''
                
                # Skip empty lines and comments
                if not key or key.startswith('#'):
                    logger.debug(f"Line {line_number}: Skipping comment or empty line")
                    continue
                
                # Parse wait time
                try:
                    wait = float(line['wait'] or 500.0)
                except ValueError:
                    logger.warning(f"Line {line_number}: Invalid wait time '{line['wait']}', using default 500ms")
                    wait = 500.0
                
                logger.info(f"Line {line_number}: Executing '{key}' with {wait}ms wait")
                
                # Send command
                if not tvcon.send(config, key, wait):
                    logger.error(f"Line {line_number}: Failed to execute command '{key}'")
                    return False
        
        logger.info(f"Macro execution completed successfully: {filename}")
        return True
        
    except (FileNotFoundError, IOError) as e:
        logger.error(f'Failed to read macro file {filename}: {e}')
        return False
    except csv.Error as e:
        logger.error(f'CSV parsing error in {filename}: {e}')
        return False
    except Exception as e:
        logger.error(f'Unexpected error executing macro {filename}: {e}')
        return False
