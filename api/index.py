import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
from typing import List, Dict
from groq import Groq
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='../templates')

class SearchValidationSystem:
    def __init__(self, groq_api_key: str):
        """Initialize the system with Groq API key."""
        self.groq_client = Groq(api_key=groq_api_key)
        self.search_results_cache = {}

    def transform_query(self, query: str) -> str:
        """Transform the user query into a Bing-searchable query using LLaMA."""
        prompt = f"Transform the following query into a more suitable format for Bing search: {query}"

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=50
            )

            if response.choices and response.choices[0].message.content:
                transformed_query = response.choices[0].message.content.strip()
                return transformed_query

        except requests.exceptions.RequestException as e:
            print(f"Request error in query transformation: {e}")

        return query  # Fallback to original query if transformation fails

    def fetch_bing_results(self, query: str, num_results: int = 10) -> List[Dict]:
        """Fetch search results from Bing by scraping the search results page."""
        url = f"https://www.bing.com/search?q={query}"
        results = []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the search result elements
            search_results = soup.find_all('li', class_='b_algo', limit=num_results)

            for result in search_results:
                title = result.find('h2').get_text(strip=True)
                result_url = result.find('a')['href']
                description = result.find('p').get_text(strip=True) if result.find('p') else ""

                results.append({
                    'url': result_url,
                    'title': title,
                    'description': description,
                    'timestamp': datetime.now().isoformat()
                })

        except Exception as e:
            print(f"Error in Bing scraping: {e}")
            print(f"Response text: {response.text}")  # Log the response text for debugging

        return results

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

        Please analyze the above information and provide an answer for the query and list any reference websites if needed.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                model="llama-3.1-8b-instant",
                temperature=1,
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

        # Step 1: Transform the user query
        transformed_query = self.transform_query(query)

        # Step 2: Fetch search results from Bing using the transformed query
        search_results = self.fetch_bing_results(transformed_query)
        if not search_results:
            return {"error": "No search results found"}

        # Step 3: Validate the search results and generate an answer
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
