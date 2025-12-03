FROM node:18-alpine AS builder

WORKDIR /app

# 의존성 설치
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 소스 코드 복사 및 빌드
COPY . .
RUN npm run build

# Nginx를 사용한 프로덕션 서버
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 파일 권한 설정 (nginx 사용자가 읽을 수 있도록)
RUN chmod -R 755 /usr/share/nginx/html && \
    chown -R nginx:nginx /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
