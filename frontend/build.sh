#!/bin/bash
# Auto-increment build number and create build

# Increment build number
if [ -f build-number.txt ]; then
  BUILD=$(cat build-number.txt)
else
  BUILD=0
fi
NEW_BUILD=$((BUILD + 1))
echo $NEW_BUILD > build-number.txt

# Generate build config
mkdir -p src/config
cat > src/config/build.ts << BUILDEOF
// Auto-generated build number - increments with each build
export const BUILD_NUMBER = ${NEW_BUILD};
export const BUILD_DATE = '$(date +"%Y-%m-%d %H:%M:%S")';
BUILDEOF

echo "🔨 Building version $NEW_BUILD..."

# Run the actual build
npm run build

echo "✅ Build $NEW_BUILD complete!"
