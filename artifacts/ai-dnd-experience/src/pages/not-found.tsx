import { Card, CardContent } from '@/components/ui/card';
import { AlertCircle } from 'lucide-react';

const homePath = import.meta.env.BASE_URL || '/';

export default function NotFound() {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gray-50">
      <Card className="w-full max-w-md mx-4">
        <CardContent className="pt-6">
          <div className="flex mb-4 gap-2">
            <AlertCircle className="h-8 w-8 text-red-500" />
            <h1 className="text-2xl font-bold text-gray-900">
              Bu sayfa bulunamadı.
            </h1>
          </div>

          <p className="mt-4 text-sm text-gray-600">
            Aradığın kapı bu yolda yok.
          </p>
          <a
            href={homePath}
            className="mt-4 inline-block rounded bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700"
          >
            Ana ekrana dön
          </a>
        </CardContent>
      </Card>
    </div>
  );
}
