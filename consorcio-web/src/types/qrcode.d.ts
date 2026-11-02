declare module 'qrcode' {
  interface QrStringOptions {
    readonly type: 'svg';
    readonly margin?: number;
  }
  const QRCode: {
    toString(text: string, options: QrStringOptions): Promise<string>;
  };
  export default QRCode;
}
