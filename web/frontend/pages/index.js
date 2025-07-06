import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { Map, Raster, Line } from '@carbonplan/maps'
import { useColormap } from '@carbonplan/colormaps'

const Index = () => {
  const router = useRouter();
  const colormap = useColormap('warm')

  useEffect(() => {
    router.push('/overview');
  }, [router]);

  return null;
}

export default Index
