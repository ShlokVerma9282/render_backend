from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
import re
from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.models.partner_type import PartnerType
from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
from paapi5_python_sdk.models.search_items_resource import SearchItemsResource
from paapi5_python_sdk.rest import ApiException
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, template_folder='templates')
CORS(app)

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Gemini API configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.0-pro')

# Amazon API configuration
access_key = os.getenv('AMAZON_ACCESS_KEY')
secret_key = os.getenv('AMAZON_SECRET_KEY')
partner_tag = os.getenv('AMAZON_PARTNER_TAG')
host = os.getenv('AMAZON_HOST')
region = os.getenv('AMAZON_REGION')

all_gift_ideas = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_gift_idea', methods=['POST'])
def generate_gift_idea():
    try:
        data = request.json
        logging.debug(f'Received data: {data}')
        
        prompt_text = create_prompt_from_data(data)
        logging.debug(f'Generated prompt: {prompt_text}')
        
        response = model.generate_content(prompt_text)
        logging.debug(f'Gemini API response: {response.text}')
        
        cleaned_text = clean_text(response.text)
        logging.debug(f'Cleaned text: {cleaned_text}')
        
        gift_ideas = process_and_structure_gift_ideas(cleaned_text)
        logging.debug(f'Processed gift ideas: {gift_ideas}')
        
        unique_gift_ideas = filter_unique_gift_ideas(gift_ideas)
        logging.debug(f'Unique gift ideas: {unique_gift_ideas}')
        
        all_gift_ideas.extend(unique_gift_ideas)
        
        # Perform search
        search_results = perform_search(unique_gift_ideas)
        logging.debug(f'Search results: {search_results}')
        
        return jsonify(search_results)

    except Exception as e:
        logging.error(f'Error generating gift ideas: {e}')
        return jsonify({"error": f"Error generating gift ideas: {e}"}), 500

def perform_search(gift_ideas):
    keywords = [item['keyword'] for item in gift_ideas]
    results = []

    default_api = DefaultApi(access_key=access_key, secret_key=secret_key, host=host, region=region)

    for keyword in keywords:
        search_items_request = SearchItemsRequest(
            partner_tag=partner_tag,
            partner_type=PartnerType.ASSOCIATES,
            keywords=keyword.strip(),
            search_index="All",
            item_count=1,
            resources=[
                SearchItemsResource.ITEMINFO_TITLE,
                SearchItemsResource.OFFERS_LISTINGS_PRICE,
                SearchItemsResource.IMAGES_PRIMARY_LARGE,
            ],
        )

        try:
            response = default_api.search_items(search_items_request)
            logging.debug(f'Amazon API response for keyword "{keyword}": {response}')
            
            if response.search_result and response.search_result.items:
                item = response.search_result.items[0]
                result = {
                    'name': keyword,
                    'title': item.item_info.title.display_value,
                    'image': item.images.primary.large.url,
                    'price': item.offers.listings[0].price.display_amount,
                    'url': item.detail_page_url,
                    'reason': gift_ideas[keywords.index(keyword)]['reason']
                }
                results.append(result)
            else:
                results.append({'error': f'No items found for keyword: {keyword}'})

        except ApiException as e:
            logging.error(f'Amazon API exception: {e}')
            results.append({'error': str(e)})

    logging.debug(f'Search results: {results}')
    return results

def create_prompt_from_data(data):
    age = data.get('age', '')
    gender = data.get('gender', '')
    occasion = data.get('occasion', '')
    recipient_type = data.get('recipient_type', '')
    categories = data.get('categories', [])
    price_range = data.get('price_range', '')
    prompt = data.get('prompt', '')

    if prompt:
        return create_search_prompt(prompt)
    else:
        return create_prompt(age, gender, occasion, recipient_type, categories, price_range)

def create_prompt(age, gender, occasion, recipient_type, categories, price_range):
    prompt_parts = [
        "You are an expert in finding gifts for Indian people. Provide me a list of 6 popular and trending different products that can be searched using the product name. Each product should include the detailed product name, company, model, and price."
    ]

    if age:
        prompt_parts.append(f"for a {age}-year-old")
    if recipient_type:
        prompt_parts.append(recipient_type)
    if gender:
        prompt_parts.append(f"who is {gender}")
    if categories:
        prompt_parts.append(f"and loves {', '.join(categories)} items")
    if occasion:
        prompt_parts.append(f"suitable for {occasion}")
    if price_range:
        prompt_parts.append(f"within the price range {price_range}")

    prompt_parts.append(
        "These gifts should be popular among Indian people and available on e-commerce websites like Amazon India. Ensure that each product is followed by its detailed product name, company, model, price, and a convincing reason for its selection. Ensure that the products are listed without any special characters such as *, -, or numbering. Here is an example:"
    )
    prompt_parts.append(
        "Product_name: RVA Cute Flower Shaped Floor Cushion for Kids Room Living Room, Bedroom Furnishing Velvet Throw Pillow Cushion for Home Decoration Kids Girls Women Gift "
    )
    prompt_parts.append(
        "Reason: Chosen for its cute design, suitable for kids and home decoration, and its popularity on Indian e-commerce sites."
    )
    prompt_parts.append(
        "Generate 6 products with detailed product name, company, model, price, and reason for selection as a gift idea. Each reason should be just below the product name."
    )

    return ' '.join(prompt_parts)

def create_search_prompt(textdata):
    return (
        f"You are an expert in finding gifts for Indian people. Based on the following input: '{textdata}', provide me with a list of 6 popular and trending products in India that would make excellent gifts for Indian people. "
        f"These products should be available for purchase on major Indian e-commerce websites like Amazon India. Ensure that the list includes detailed product names, company, model, price, followed by a convincing reason for selecting each product as a gift idea. "
        f"The reason should explain why the product is a good gift for Indian consumer. Provide the output in the following format:\n\n"
        f"Product_name:\nReason:\n"
        f"Product_name:\nReason:\n"
        f"Product_name:\nReason:\n"
        f"Product_name:\nReason:\n"
        f"Product_name:\nReason:\n"
        f"Product_name:\nReason:\n"
        f"Here is an example:\n"
        f"Product_name: RVA Cute Flower Shaped Floor Cushion for Kids Room Living Room, Bedroom Furnishing Velvet Throw Pillow Cushion for Home Decoration Kids Girls Women Gift \n"
        f"Reason: Chosen for its cute design, suitable for kids and home decoration, and its popularity on Indian e-commerce sites."
    )

def filter_unique_gift_ideas(new_gift_ideas):
    return [idea for idea in new_gift_ideas if idea not in all_gift_ideas]

def clean_text(text):
    # Removing unwanted characters
    text = re.sub(r'[*-]', '', text)
    text = re.sub(r'\d+\.\s*', '', text)
    return text

def process_and_structure_gift_ideas(text):
    product_names = []
    reasons = []

    # Splitting text by new lines to separate product names and reasons
    lines = text.split('\n')
    product_line = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "Reason:" in line:
            reasons.append(line.replace("Reason:", "").strip())
            if product_line is not None:
                product_names.append(product_line)
            product_line = None
        else:
            if product_line is None:
                product_line = line
            else:
                product_line += " " + line

    # Remove "Product_name: " prefix from product names
    product_names = [remove_product_name_prefix(name) for name in product_names]

    logging.debug(f'Extracted product names: {product_names}')
    logging.debug(f'Extracted reasons: {reasons}')

    combined_gift_ideas = []
    for name, reason in zip(product_names, reasons):
        combined_gift_ideas.append({
            "keyword": name,
            "reason": reason
        })

    logging.debug(f'Combined gift ideas: {combined_gift_ideas}')
    return combined_gift_ideas

def remove_product_name_prefix(name):
    if name.startswith("Product_name:"):
        return name[len("Product_name:"):].strip()
    return name

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
