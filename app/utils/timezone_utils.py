from datetime import datetime, timedelta
import pytz
import logging
import re

def extract_timezone_offset(timezone_str: str) -> tuple:
    """Extract timezone offset components from GMT format string"""
    # Clean up timezone string
    timezone_str = timezone_str.replace(' ', '')  # Remove spaces
    match = re.match(r'GMT([+-])(\d{2}):(\d{2})', timezone_str)
    if not match:
        return ('+', 0, 0)
    
    sign = match.group(1)
    hours = int(match.group(2))
    minutes = int(match.group(3))
    return (sign, hours, minutes)

def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string in various formats"""
    formats = [
        '%Y-%m-%dT%H:%M:%S.%fZ',  # With milliseconds
        '%Y-%m-%dT%H:%M:%SZ',     # Without milliseconds
        '%Y-%m-%dT%H:%M:%S',      # Basic ISO format
        '%Y-%m-%dT%H:%M:%S.%f'    # With milliseconds, no Z
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str.rstrip('Z'), fmt.rstrip('Z'))
        except ValueError:
            continue
    raise ValueError(f"Unable to parse datetime: {dt_str}")

def convert_utc_to_timezone(dt: str, timezone_str: str) -> str:
    """Convert UTC datetime to specified timezone"""
    if not dt or not timezone_str:
        return ''
    
    try:
        # Parse UTC datetime
        utc_dt = datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S')
        
        # Clean timezone string
        tz = timezone_str.strip()
        
        # Handle formats: "GMT+05:30", "GMT 05:30", "GMT+5:30"
        if tz.startswith('GMT'):
            # Remove GMT prefix and any spaces
            offset_str = tz[3:].strip()
            
            # Add '+' if no sign present
            if not offset_str.startswith('+') and not offset_str.startswith('-'):
                offset_str = '+' + offset_str
            
            # Split hours and minutes
            sign = offset_str[0]
            parts = offset_str[1:].split(':')
            if len(parts) != 2:
                logging.error(f"Invalid offset format: {timezone_str}")
                return ''
                
            hours = int(parts[0])
            minutes = int(parts[1])
            
            # Calculate offset
            total_minutes = (hours * 60 + minutes) * (1 if sign == '+' else -1)
            local_dt = utc_dt + timedelta(minutes=total_minutes)
            
            # Format result
            return f"{local_dt.strftime('%Y-%m-%dT%H:%M:%S.000')}{sign}{hours:02d}:{minutes:02d}"
            
        logging.error(f"Invalid timezone format (must start with GMT): {timezone_str}")
        return ''
        
    except Exception as e:
        logging.error(f"Error converting timezone for '{dt}' with '{timezone_str}': {str(e)}")
        return ''
