import type {Metadata,Viewport} from 'next';
import './globals.css';
export const metadata:Metadata={title:'Village · Life, together.',description:'A private place for your church family to know one another, invite one another in, and lend a hand.',manifest:'/manifest.webmanifest',robots:{index:false,follow:false}};
export const viewport:Viewport={width:'device-width',initialScale:1,viewportFit:'cover',themeColor:'#f8f4ed'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
