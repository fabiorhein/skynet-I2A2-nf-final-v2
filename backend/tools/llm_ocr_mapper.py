"""LLM-assisted OCR mapper using Google Gemini (google-generativeai).

This module provides a small wrapper that attempts to call the Gemini API
when a `GOOGLE_API_KEY` environment variable is present. If not present
the mapper falls back to a lightweight heuristic/mocked mapper so tests
and local runs without keys do not fail.

The mapper instructs the model to return strict JSON describing the
document fields. We do cautious parsing of the model output to recover
JSON even when the model adds explanatory text.
"""
from typing import Dict, Any
import os
import json
import re


class LLMOCRMapper:
    def __init__(self, model: str = "gemini-2.5-flash"):  # Modelo rápido e estável para processamento de texto
        self.model = model
        self.available = False
        self._client = None
        
        try:
            # Importa a função _get do config.py que já lê do secrets.toml
            from config import _get
            
            # Obtém a chave da API usando o config.py
            self.api_key = _get('GOOGLE_API_KEY')
            
            if not self.api_key:
                print("Aviso: Chave da API não encontrada nas configurações")
                return
                
            # Configura o cliente da API
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=self.api_key)
            self._client = genai
            self.available = True
            
        except ImportError as e:
            print(f"Erro ao importar config: {str(e)}")
            print("Certifique-se de que o módulo config.py está no PYTHONPATH")
        except Exception as e:
            print(f"Erro ao configurar o cliente da API: {str(e)}")
            self.available = False

    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM and return a text response.

        Uses the latest Google Generative AI API (v0.4.0+).
        """
        if self._client is None:
            print("LLM client not configured")
            return ""

        try:
            # For Gemini 2.5 Flash model
            model = self._client.GenerativeModel(self.model)
            
            # Configuração de geração para melhorar a saída JSON
            generation_config = {
                "temperature": 0.1,  # Reduz a criatividade para respostas mais previsíveis
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
            }
            
            # Envia o prompt para o modelo
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
            )
            
            print("Resposta bruta do modelo:", response)  # Log para depuração
            
            # Extrai o texto da resposta
            if hasattr(response, 'text'):
                text = response.text
            elif hasattr(response, 'parts'):
                text = ' '.join(part.text for part in response.parts if hasattr(part, 'text'))
            else:
                text = str(response)
            
            # Tenta extrair apenas o JSON da resposta, se necessário
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json_match.group(0)
                
            return text
                
        except Exception as e:
            print(f"Erro na chamada do LLM: {str(e)}")
            print(f"Tipo do erro: {type(e).__name__}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print(f"Resposta de erro da API: {e.response.text}")
            return ""  # Retorna string vazia para ativar o fallback

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Try to extract a JSON object from model text.

        The model may add surrounding explanation; this attempts several
        heuristics to locate the JSON substring and parse it.
        """
        if not text.strip():
            print("Aviso: Texto vazio recebido para extração de JSON")
            return {}
            
        print(f"Tentando extrair JSON de: {text[:200]}...")  # Log parcial para depuração

        # 1. Tentativa direta
        try:
            result = json.loads(text)
            print("JSON extraído com sucesso na primeira tentativa")
            return result
        except json.JSONDecodeError as e:
            print(f"Falha na primeira tentativa de parse JSON: {str(e)}")

        # 2. Tenta encontrar JSON dentro de blocos de código markdown
        markdown_match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if markdown_match:
            try:
                result = json.loads(markdown_match.group(1))
                print("JSON extraído de bloco de código markdown")
                return result
            except json.JSONDecodeError as e:
                print(f"Falha ao extrair JSON de bloco markdown: {str(e)}")

        # 3. Tenta encontrar qualquer objeto JSON na string
        json_match = re.search(r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}', text, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(0)
                # Tenta limpar a string JSON antes de fazer o parse
                json_str = json_str.replace('\n', ' ').replace('\r', '').replace('\t', ' ')
                # Remove múltiplos espaços
                json_str = re.sub(' +', ' ', json_str)
                result = json.loads(json_str)
                print("JSON extraído com regex avançada")
                return result
            except json.JSONDecodeError as e:
                print(f"Falha ao extrair JSON com regex: {str(e)}")
                print(f"String problemática: {json_str[:200]}...")

        # 4. Tenta limpar e corrigir o JSON manualmente
        try:
            # Remove linhas que não fazem parte do JSON
            lines = [line for line in text.split('\n') 
                    if line.strip() and not line.strip().startswith(('//', '#', '/*', '*'))]
            cleaned_text = '\n'.join(lines)
            # Tenta remover caracteres inválidos
            cleaned_text = re.sub(r'[\x00-\x1F\x7F]', ' ', cleaned_text)
            result = json.loads(cleaned_text)
            print("JSON extraído após limpeza")
            return result
        except Exception as e:
            print(f"Falha ao extrair JSON após limpeza: {str(e)}")

        print("Não foi possível extrair um JSON válido do texto")
        return {}  # Retorna um dicionário vazio para evitar erros

    def _heuristic_map(self, text: str) -> Dict[str, Any]:
        """A very small heuristic mapper used when LLM is not available.

        This avoids failing tests and gives a reasonable fallback for local
        development without credentials.
        """
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        doc: Dict[str, Any] = {'raw_text': text, 'emitente': {}, 'destinatario': {}, 'itens': [], 'impostos': {}, 'total': None}
        import re
        cnpj_re = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})")
        date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
        money_re = re.compile(r"([\d.,]+)\s*$")
        for ln in lines:
            m = cnpj_re.search(ln)
            if m and not doc['emitente'].get('cnpj'):
                doc['emitente']['cnpj'] = re.sub(r"\D", "", m.group(1))
                continue
            m = date_re.search(ln)
            if m and not doc.get('data_emissao'):
                doc['data_emissao'] = m.group(1)
                continue
            if 'total' in ln.lower() or 'valor' in ln.lower():
                m = money_re.search(ln)
                if m:
                    try:
                        doc['total'] = float(m.group(1).replace('.', '').replace(',', '.'))
                    except Exception:
                        pass
        return doc

    def map_ocr_text(self, text: str) -> Dict[str, Any]:
        """Map OCR text to structured document using LLM (Gemini) or heuristic fallback.

        Returns a dictionary with keys similar to the XML parser output.
        """
        if not text or not text.strip():
            return {'error': 'empty_text', 'raw_text': text}

        # If the client isn't available, use heuristic mapper (safe for tests)
        if not self.available:
            return self._heuristic_map(text)

        # Try LLM mapping if available, otherwise fall back to heuristics
        if self.available and self.api_key:
            try:
                # Build prompt instructing the model to reply with JSON only
                prompt = (
                    "Extraia os campos principais de uma nota fiscal a partir do texto OCR. "
                    "Responda SOMENTE um objeto JSON válido sem explicações. "
                    "O JSON deve conter, quando possível, as chaves: numero, data_emissao, "
                    "emitente {razao_social, cnpj, inscricao_estadual}, destinatario {razao_social, cnpj_cpf}, "
                    "itens (lista de objetos com descricao, quantidade, valor_unitario, valor_total), "
                    "impostos {icms, pis, cofins, ipi}, total. "
                    "Se algum campo não estiver presente, use null ou omit.\n\n"
                )
                prompt += "TEXTO:\n" + text + "\n\nJSON:\n"

                resp_text = self._call_llm(prompt)
                
                # Se a resposta estiver vazia, usar o mapeador heurístico
                if not resp_text.strip():
                    return self._heuristic_map(text)
                    
                parsed = self._extract_json(resp_text)
                
                # Se não conseguirmos extrair um JSON válido, usar o mapeador heurístico
                if not isinstance(parsed, dict):
                    return self._heuristic_map(text)
                    
                return parsed
                
            except Exception as e:
                print(f"Error in LLM mapping: {str(e)}")
                print("Falling back to heuristic mapper...")
                
        # Se chegamos aqui, usar o mapeador heurístico
        return self._heuristic_map(text)