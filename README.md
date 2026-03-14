# Naver Real Estate Tracker

네이버 부동산 매물을 자동으로 조회하여  
**급매 및 단지 최저가 매물을 추적하는 웹 서비스**입니다.

FastAPI 기반으로 구현되어 있으며,  
사용자가 선택한 지역의 아파트 매물을 조회하고  
최저가 대비 가격 차이를 계산하여 보여줍니다.

---

# Features

- 네이버 부동산 매물 조회
- 단지별 매물 자동 수집
- 단지 최저가 계산
- 급매 탐지
- FastAPI 기반 웹 서비스
- 간단한 웹 UI 제공

---

# Tech Stack

Backend
- Python
- FastAPI
- Uvicorn

Data Processing
- Requests
- JSON parsing

Frontend
- HTML
- Jinja2 Template

---

# Project Structure

project-root  
 ├ app  
 │   ├ main.py  
 │   ├ fetcher.py  
 │   ├ parser.py  
 │   ├ config.py  
 │   ├ history.py  
 │   └ templates  
 │        └ index.html  
 │
 ├ requirements.txt  
 └ README.md  

---

# Installation

### 1. Clone
git clone https://github.com/YOUR_ID/naver-realestate-tracker.git
cd naver-realestate-tracker

### 2. Virtual Environment
python -m venv .venv
.venv\Scripts\activate


### 3. Install Dependencies
pip install -r requirements.txt


