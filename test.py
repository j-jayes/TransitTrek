import requests

url = "https://api.blocket.se/motor-query-service/v1/view/1002329316"

response = requests.get(url)
print(response.text)