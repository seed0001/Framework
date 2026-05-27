import psutil
import platform

def run_diagnostics(check_type='disk'):
    """Run system diagnostics based on the specified check type."""
    try:
        if check_type == 'disk':
            disk_usage = psutil.disk_usage('/')
            return {
                'total': round(disk_usage.total / (1024**3), 2),  # Convert to GB
                'used': round(disk_usage.used / (1024**3), 2),
                'free': round(disk_usage.free / (1024**3), 2),
                'percent': disk_usage.percent,
                'message': 'Disk usage information in GB.'
            }
        elif check_type == 'memory':
            memory = psutil.virtual_memory()
            return {
                'total': round(memory.total / (1024**3), 2),  # Convert to GB
                'used': round(memory.used / (1024**3), 2),
                'free': round(memory.free / (1024**3), 2),
                'percent': memory.percent,
                'message': 'Memory usage information in GB.'
            }
        elif check_type == 'cpu':
            cpu_percent = psutil.cpu_percent(interval=1)
            return {
                'percent': cpu_percent,
                'message': 'CPU usage percentage.'
            }
        else:
            return {'error': f'Unsupported check type: {check_type}'}
    except Exception as e:
        return {'error': f'Failed to run diagnostics: {str(e)}'}

if __name__ == '__main__':
    result = run_diagnostics('disk')
    print(result)
