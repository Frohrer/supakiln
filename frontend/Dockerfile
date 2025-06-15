FROM node:18-alpine

WORKDIR /app

# Install dependencies first (better caching)
COPY package*.json ./
RUN npm install

# Copy the rest of the application
COPY . .

# Accept build arguments for environment variables
ARG VITE_API_URL
ARG VITE_CF_CLIENT_ID
ARG VITE_CF_CLIENT_SECRET
ARG VITE_CF_ACCESS_TOKEN

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_CF_CLIENT_ID=$VITE_CF_CLIENT_ID
ENV VITE_CF_CLIENT_SECRET=$VITE_CF_CLIENT_SECRET
ENV VITE_CF_ACCESS_TOKEN=$VITE_CF_ACCESS_TOKEN

# Build the application with environment variables
RUN npm run build

# Install serve to run the application
RUN npm install -g serve

# Expose port 3000
EXPOSE 3000

# Start the application
CMD ["serve", "-s", "dist", "-l", "3000"] 