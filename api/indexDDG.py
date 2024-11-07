import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import time
from typing import List, Dict
from groq import Groq
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='../templates')

class SearchValidationSystem:
    def __init__(self, groq_api_key: str):
        """Initialize the system with Groq API key."""
        self.groq_client = Groq(api_key=groq_api_key)
        self.search_results_cache = {}

    def fetch_duckduckgo_lite_results(self, query: str, num_results: int = 5) -> List[Dict]:
        """Fetch search results from Bing instead of DuckDuckGo Lite."""
        url = "https://www.bing.com/search"
        results = []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            response = requests.get(url, headers=headers, params={'q': query})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            links = soup.find_all('li', class_='b_algo', limit=num_results)

            for link in links:
                title = link.find('h2').get_text(strip=True)
                result_url = link.find('a')['href']

                if result_url and title:
                    content = self._fetch_page_content(result_url)
                    results.append({
                        'url': result_url,
                        'title': title,
                        'description': content[:150] + "...",
                        'timestamp': datetime.now().isoformat()
                    })
                time.sleep(1)

        except Exception as e:
            print(f"Error in Bing search: {e}")

        return results

    def _fetch_page_content(self, url: str) -> str:
        """Fetch and parse content from a webpage."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()

            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            if main_content:
                paragraphs = main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                content = ' '.join(p.get_text(strip=True) for p in paragraphs)
                return content[:5000]
            return ""

        except Exception as e:
            print(f"Error fetching page content from {url}: {e}")
            return ""

    def validate_with_llama(self, query: str, search_results: List[Dict]) -> Dict:
        """Validate search results using LLaMA through Groq."""
        if not search_results:
            return {"error": "No valid search results to analyze"}

        context = "\n".join([f"Source {i+1} ({result['url']}):\nTitle: {result['title']}\nDescription: {result['description'][:200]}..."
                             for i, result in enumerate(search_results)])

        prompt = f"""
        Query: {query}

        Context from multiple sources:
        {context}

        Please analyze the above information and provide the answer for the query. And list any references if any.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=2048
            )

            # Debugging: Print the raw response
            print("LLaMA Response:", response)

            if not response.choices or not response.choices[0].message.content:
                return {
                    "summary": "Error in validation process",
                    "validation": "Empty response from Groq API",
                    "inconsistencies": [],
                    "references": []
                }

            validation_response = response.choices[0].message.content

            # Debugging: Print the validation response
            print("Validation Response:", validation_response)

            try:
                validation_data = json.loads(validation_response)
                if isinstance(validation_data, dict):
                    return validation_data
            except json.JSONDecodeError:
                pass

            return {
                "validation": validation_response,
                
            }

        except requests.exceptions.RequestException as e:
            print(f"Request error in LLaMA validation: {e}")
            return {
                "summary": "Error in validation process",
                "validation": str(e),
                "inconsistencies": [],
                "references": []
            }

    def search_and_validate(self, query: str) -> Dict:
        """Main method to perform search and validation."""
        if query in self.search_results_cache:
            print("Using cached results...")
            return self.search_results_cache[query]

        search_results = self.fetch_duckduckgo_lite_results(query)
        if not search_results:
            return {"error": "No search results found"}

        validation_results = self.validate_with_llama(query, search_results)

        final_results = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "search_results": search_results,
            "validation": validation_results
        }

        self.search_results_cache[query] = final_results
        return final_results

# Instantiate the SearchValidationSystem globally
groq_api_key = "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"  # Replace with your Groq API key
system = SearchValidationSystem(groq_api_key)

@app.route('/')
def index():
    """Render the main UI page."""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Endpoint to perform search and validation."""
    data = request.json
    query = data.get('query')

    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    results = system.search_and_validate(query)
    return jsonify(results)

if __name__ == "__main__":
    app.run()
