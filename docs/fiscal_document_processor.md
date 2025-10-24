# Processador de Documentos Fiscais

O `FiscalDocumentProcessor` é uma classe Python projetada para extrair texto e dados estruturados de documentos fiscais em vários formatos, incluindo PDFs e imagens. Ele utiliza OCR (Reconhecimento Óptico de Caracteres) para processar documentos digitalizados e extrair informações relevantes como emitente, destinatário, itens e impostos.

## Funcionalidades

- Extração de texto de imagens e PDFs usando Tesseract OCR
- Identificação automática do tipo de documento fiscal (NFe, NFCe, CTe, MDFe)
- Extração estruturada de campos como:
  - Dados do emitente (nome, CNPJ, inscrição estadual)
  - Dados do destinatário (nome, CPF/CNPJ)
  - Itens do documento (descrição, quantidade, valor unitário, valor total)
  - Impostos (ICMS, PIS, COFINS, IPI)
  - Chave de acesso e protocolo de autorização
- Suporte a processamento em lote
- Integração com LLM para melhorar a precisão da extração (opcional)

## Requisitos

- Python 3.8+
- Tesseract OCR instalado no sistema
- Dependências do Python listadas em `requirements.txt`
- (Opcional) Chave de API do Google para usar o LLM

## Instalação

1. Instale as dependências do Python:

```bash
pip install -r requirements.txt
```

2. Instale o Tesseract OCR:

- **Windows**: Baixe o instalador do [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- **Linux**: `sudo apt-get install tesseract-ocr-por`
- **macOS**: `brew install tesseract tesseract-lang`

3. (Opcional) Configure a chave da API do Google para usar o LLM:

Crie ou edite o arquivo `.streamlit/secrets.toml` na raiz do projeto e adicione:

```toml
GOOGLE_API_KEY = "sua_chave_aqui"
```

## Uso Básico

### Processando um único documento

```python
from backend.tools.fiscal_document_processor import FiscalDocumentProcessor

# Cria uma instância do processador
processor = FiscalDocumentProcessor()

# Processa um documento
result = processor.process_document("caminho/para/documento.pdf")

# Exibe os resultados
print(f"Tipo de documento: {result.get('document_type')}")
print(f"Número: {result.get('numero')}")
print(f"Emitente: {result.get('emitente', {}).get('razao_social')}")
print(f"Valor Total: R$ {result.get('valor_total', 0):.2f}")
```

### Usando a linha de comando

O projeto inclui um script de exemplo que pode ser executado diretamente:

```bash
# Processa um documento e exibe os resultados no console
python -m examples.process_document documentos/nota_fiscal.pdf

# Processa um documento e salva os resultados em um arquivo JSON
python -m examples.process_document documentos/nota_fiscal.pdf --output resultado.json
```

## Formatos Suportados

- **Imagens**: PNG, JPG, JPEG, TIFF, BMP
- **Documentos**: PDF (com ou sem camada de texto)

## Processamento em Lote

Para processar vários documentos de uma vez:

```python
from pathlib import Path
from backend.tools.fiscal_document_processor import FiscalDocumentProcessor

# Diretório com os documentos a serem processados
input_dir = Path("documentos/")
output_dir = Path("resultados/")
output_dir.mkdir(exist_ok=True)

# Processa todos os arquivos suportados no diretório
processor = FiscalDocumentProcessor()
for file_path in input_dir.glob("*"):
    if file_path.suffix.lower() in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        print(f"Processando: {file_path.name}")
        try:
            result = processor.process_document(file_path)
            
            # Salva o resultado em um arquivo JSON
            output_file = output_dir / f"{file_path.stem}_resultado.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
            print(f"  → Resultado salvo em: {output_file}")
            
        except Exception as e:
            print(f"  → Erro ao processar {file_path.name}: {str(e)}")
```

## Integração com o Streamlit

O processador pode ser facilmente integrado a uma aplicação web usando Streamlit:

```python
import streamlit as st
from backend.tools.fiscal_document_processor import FiscalDocumentProcessor

def main():
    st.title("Processador de Documentos Fiscais")
    
    uploaded_file = st.file_uploader(
        "Carregue um documento fiscal (PDF ou imagem)",
        type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
    )
    
    if uploaded_file is not None:
        with st.spinner("Processando documento..."):
            # Salva o arquivo temporariamente
            temp_file = Path("temp_upload") / uploaded_file.name
            temp_file.parent.mkdir(exist_ok=True)
            
            with open(temp_file, "wb") as f:
                f.write(uploaded_file.getvalue())
            
            # Processa o documento
            try:
                processor = FiscalDocumentProcessor()
                result = processor.process_document(temp_file)
                
                # Exibe os resultados
                st.success("Documento processado com sucesso!")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Emitente")
                    st.json(result.get('emitente', {}))
                
                with col2:
                    st.subheader("Destinatário")
                    st.json(result.get('destinatario', {}))
                
                st.subheader("Itens")
                st.dataframe(result.get('itens', []))
                
                st.subheader("Impostos")
                st.json(result.get('impostos', {}))
                
            except Exception as e:
                st.error(f"Erro ao processar o documento: {str(e)}")
            finally:
                # Remove o arquivo temporário
                try:
                    temp_file.unlink()
                except:
                    pass

if __name__ == "__main__":
    main()
```

## Personalização

### Idiomas Suportados

Por padrão, o processador está configurado para português. Para usar outro idioma, especifique-o ao criar a instância:

```python
# Para inglês
processor = FiscalDocumentProcessor(language='eng')

# Para espanhol
processor = FiscalDocumentProcessor(language='spa')
```

### Configuração do Tesseract

Se o Tesseract não estiver no PATH do sistema, você pode especificar o caminho manualmente:

```python
from backend.tools.fiscal_document_processor import FiscalDocumentProcessor
import pytesseract

# Especifica o caminho para o executável do Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

# Agora crie a instância do processador
processor = FiscalDocumentProcessor()
```

## Solução de Problemas

### O Tesseract não está sendo encontrado

Certifique-se de que o Tesseract está instalado e no PATH do sistema. Se não estiver, especifique o caminho manualmente conforme mostrado acima.

### Baixa qualidade de reconhecimento

- Certifique-se de que as imagens estão nítidas e com boa iluminação
- Tente aumentar o DPI ao processar PDFs: `processor._extract_text_from_pdf("documento.pdf", dpi=400)`
- Experimente ajustar o pré-processamento da imagem no método `_preprocess_image`

### Erros ao processar PDFs

Alguns PDFs podem estar protegidos por senha ou ter formatos complexos. Nesses casos, tente converter o PDF para imagens antes de processá-lo.

## Licença

Este projeto está licenciado sob a licença MIT. Consulte o arquivo LICENSE para obter mais informações.
