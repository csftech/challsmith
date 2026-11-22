FROM node:26.13.1-alpine3.24
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY entrypoint.sh ./
COPY app app
RUN npm run build
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["npm", "start"]
