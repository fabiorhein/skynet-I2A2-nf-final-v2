import google.generativeai as genai
import os
import toml

def load_api_key():
    # 1. Tenta carregar do arquivo secrets.toml
    try:
        secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
        if os.path.exists(secrets_path):
            with open(secrets_path) as f:
                secrets = toml.load(f)
                if 'GOOGLE_API_KEY' in secrets:
                    return secrets['GOOGLE_API_KEY']
    except Exception as e:
        print(f"Aviso: Não foi possível ler o arquivo secrets.toml: {e}")
    
    # 2. Tenta da variável de ambiente
    api_key = os.environ.get('GOOGLE_API_KEY')
    if api_key:
        return api_key
        
    # 3. Tenta do arquivo .env se existir
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get('GOOGLE_API_KEY')
        if api_key:
            return api_key
    except ImportError:
        pass
    
    return None

def list_available_models():
    # Tenta carregar a chave de diferentes fontes
    api_key = load_api_key()
    
    if not api_key:
        print("ERRO: Não foi possível encontrar a chave da API.")
        print("Certifique-se de que a chave está definida em uma das seguintes fontes:")
        print("1. No arquivo .streamlit/secrets.toml (GOOGLE_API_KEY)")
        print("2. Na variável de ambiente GOOGLE_API_KEY")
        print("3. Em um arquivo .env (GOOGLE_API_KEY)")
        return
    
    print(f"Usando chave API: {api_key[:10]}...{api_key[-4:]}")
    
    try:
        genai.configure(api_key=api_key)
        print("\nListando modelos disponíveis...\n")
        
        models = genai.list_models()
        gemini_models = [m for m in models if 'gemini' in m.name.lower()]
        
        if not gemini_models:
            print("Nenhum modelo Gemini encontrado.")
            print("\nTodos os modelos disponíveis:")
            for m in models:
                print(f"- {m.name}")
            return
            
        for model in gemini_models:
            print(f"Nome: {model.name}")
            print(f"  - Suporta geração de conteúdo: {', '.join(model.supported_generation_methods) if model.supported_generation_methods else 'Nenhum'}")
            print(f"  - Descrição: {model.description}")
            print()
            
    except Exception as e:
        print(f"Erro ao listar modelos: {str(e)}")
        print("\nDicas de solução de problemas:")
        print("1. Verifique se a chave da API está correta e ativada")
        print("2. Verifique sua conexão com a internet")
        print("3. Tente gerar uma nova chave de API no Google AI Studio")

if __name__ == "__main__":
    list_available_models()
