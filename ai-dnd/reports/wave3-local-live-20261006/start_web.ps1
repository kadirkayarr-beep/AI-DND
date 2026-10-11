$env:PORT = '22785'
$env:BASE_PATH = '/ai-dnd-experience/'
Set-Location 'C:\Users\Kadir\Desktop\AI-DND-pre04-wave3'
corepack pnpm --filter @workspace/ai-dnd-experience run dev
