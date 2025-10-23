from . import extraction, classifier, analyst
from typing import Dict, Any


def run_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a task through the appropriate agent with error handling."""
    try:
        if task == 'extract':
            path = payload.get('path')
            if not path:
                return {'error': 'missing_path', 'message': 'Path is required'}
            
            extracted = extraction.extract_from_file(path)
            # Ensure extracted is a dict
            if not isinstance(extracted, dict):
                return {
                    'error': 'invalid_format',
                    'message': f'Expected dict, got {type(extracted)}',
                    'raw_text': str(extracted) if extracted else None
                }
            return extracted

        if task == 'classify':
            if not isinstance(payload, dict):
                return {
                    'tipo': 'unknown',
                    'setor': 'unknown',
                    'perfil_emitente': 'unknown',
                    'validacao': {
                        'status': 'error',
                        'issues': ['Payload inválido'],
                        'calculated_sum': 0.0
                    }
                }
            
            parsed = payload.get('parsed')
            # Handle both string and dict cases gracefully
            if isinstance(parsed, str):
                return {
                    'tipo': 'unknown',
                    'setor': 'unknown',
                    'perfil_emitente': 'unknown',
                    'validacao': {
                        'status': 'error',
                        'issues': ['Dados em formato texto, esperava dicionário'],
                        'calculated_sum': 0.0
                    }
                }
            if not isinstance(parsed, dict):
                return {
                    'tipo': 'unknown',
                    'setor': 'unknown',
                    'perfil_emitente': 'unknown',
                    'validacao': {
                        'status': 'error',
                        'issues': [f'Dados inválidos para classificação: {type(parsed)}'],
                        'calculated_sum': 0.0
                    }
                }
            return classifier.classify_document(parsed)

        if task == 'analyze':
            path = payload.get('path')
            if not path:
                return {'error': 'missing_path', 'message': 'Path is required'}
            return analyst.analyze_csv(path)

        return {'error': 'unknown_task', 'message': f'Task {task} not recognized'}
        
    except Exception as e:
        return {
            'error': 'task_failed',
            'message': str(e),
            'task': task
        }
