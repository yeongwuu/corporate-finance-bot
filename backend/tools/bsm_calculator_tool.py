import math
import re
from typing import Any
from scipy.stats import norm

def calculate_bsm_option(question: str) -> dict[str, Any]:
    normalized = question.lower().replace(" ", "")
    
    s_match = re.search(r"(?:기초자산|주가|지수|현재가|s)\s*(?:가|이|는|=)?\s*([0-9,.]+)", normalized)
    k_match = re.search(r"(?:행사가|행사가격|행사|k)\s*(?:가|이|는|=)?\s*([0-9,.]+)", normalized)
    t_match = re.search(r"(?:만기|기간|잔존기간|t)\s*(?:가|이|는|=)?\s*([0-9,.]+)\s*(?:일|년|개월|달)?", normalized)
    r_match = re.search(r"(?:이자율|무위험이자율|금리|r)\s*(?:가|이|는|=)?\s*([0-9,.]+)\s*%", normalized)
    vol_match = re.search(r"(?:변동성|표준편차|sigma|변동율)\s*(?:가|이|는|=)?\s*([0-9,.]+)\s*%", normalized)
    
    S = float(s_match.group(1).replace(",", "")) if s_match else 350.0
    K = float(k_match.group(1).replace(",", "")) if k_match else 355.0
    
    T = 30.0 / 365.0
    if t_match:
        val = float(t_match.group(1))
        unit = t_match.group(0)
        if "일" in unit:
            T = val / 365.0
        elif "개월" in unit or "달" in unit:
            T = val / 12.0
        elif "년" in unit:
            T = val
        else:
            if val > 10:
                T = val / 365.0
            else:
                T = val
                
    r = float(r_match.group(1)) / 100.0 if r_match else 0.035
    sigma = float(vol_match.group(1)) / 100.0 if vol_match else 0.20
    
    option_type = "put" if any(token in normalized for token in ["풋", "put"]) else "call"
    
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        if option_type == "call":
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
            theta = - (S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm.cdf(d2)
            rho = K * T * math.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1.0
            theta = - (S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm.cdf(-d2)
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2)
            
        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T)
        
        output = {
            "status": "ok",
            "mode": "bsm_pricing",
            "option_type": option_type,
            "S": S,
            "K": K,
            "T": T,
            "T_days": T * 365.0,
            "r": r,
            "sigma": sigma,
            "price": price,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
            "summary": f"블랙숄즈 모형을 통해 {option_type.upper()} 옵션의 이론가격과 주요 그리스(Greeks)를 산출했습니다.",
            "steps": [
                f"기초자산가격(S): {S:,.2f}",
                f"행사가격(K): {K:,.2f}",
                f"잔존만기(T): {T*365:.1f}일 ({T:.4f}년)",
                f"무위험금리(r): {r*100:.2f}%",
                f"변동성(σ): {sigma*100:.2f}%",
                f"옵션 종류: {option_type.upper()}",
                f"이론가격: {price:,.4f}",
                f"델타 (Δ): {delta:.4f}",
                f"감마 (Γ): {gamma:.4f}",
                f"세타 (Θ): {theta:.4f} (일평균 {-theta/365.0:.4f})",
                f"베가 (ν): {vega:.4f}",
                f"로 (ρ): {rho:.4f}"
            ]
        }
        return output
    except Exception as exc:
        return {
            "status": "error",
            "message": f"블랙숄즈 연산 오류: {exc}",
            "steps": ["매개변수 부호 및 로그 진수가 양수인지 점검바랍니다."]
        }
