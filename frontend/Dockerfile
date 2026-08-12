FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Empty base → browser calls same origin; nginx proxies /api
ENV VITE_API_BASE=
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.demo.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
