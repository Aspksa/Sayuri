import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const SayuriApp());
const storage = FlutterSecureStorage();
class SayuriApp extends StatelessWidget {
  const SayuriApp({super.key});
  @override Widget build(BuildContext context) => MaterialApp(
    title: 'Sayuri',
    theme: ThemeData.dark(useMaterial3: true),
    home: const ChatScreen(),
  );
}
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override State<ChatScreen> createState() => _ChatState();
}
class _ChatState extends State<ChatScreen> {
  final address = TextEditingController();
  final password = TextEditingController();
  final draft = TextEditingController();
  String server = '', token = '', active = '', status = '';
  List<dynamic> chats = [], messages = [];
  bool waiting = false;
  @override void initState() { super.initState(); restore(); }
  Future<void> restore() async {
    server = await storage.read(key: 'server') ?? '';
    token = await storage.read(key: 'token') ?? '';
    address.text = server;
    if (token.isNotEmpty) await loadChats();
    if (mounted) setState(() {});
  }
  Future<dynamic> api(String route, {String method = 'GET', Object? data}) async {
    final url = Uri.parse('${server.replaceFirst(RegExp(r"/+$"), "")}/api$route');
    final request = http.Request(method, url);
    request.headers.addAll({'Content-Type':'application/json', if(token.isNotEmpty) 'Authorization':'Bearer $token'});
    if (data != null) request.body = jsonEncode(data);
    final client = http.Client();
    try {
      final response = await http.Response.fromStream(await client.send(request));
      final result = jsonDecode(utf8.decode(response.bodyBytes));
      if (response.statusCode >= 400) throw Exception(result['detail'] ?? 'Ошибка соединения');
      return result;
    } finally { client.close(); }
  }
  Future<void> login({bool first = false}) async {
    try {
      server = address.text.trim();
      if (!server.startsWith('https://')) throw Exception('Нужен HTTPS URL сервера');
      await storage.write(key: 'server', value: server);
      if (first) await api('/auth/setup', method:'POST', data:{'password':password.text});
      final response = await api('/auth/login', method:'POST', data:{'password':password.text});
      token = response['token'];
      await storage.write(key:'token',value:token);
      password.clear();
      await loadChats();
      status = '';
    } catch (e) { status = '$e'; }
    if(mounted) setState(() {});
  }
  Future<void> loadChats() async {
    try {
      chats = await api('/chats');
      final mentors = chats.where((c)=>c['kind']=='teacher').toList()
        ..sort((a,b)=>(a['created'] as int).compareTo(b['created'] as int));
      if(mentors.isEmpty){
        final c=await api('/chats',method:'POST',data:{'title':'Общий чат','kind':'teacher'});
        active=c['id'];
      }else{
        active=mentors.first['id'];
      }
      await loadMessages();
      status='';
    }catch(e){status='$e';}
    if(mounted)setState(() {});
  }
  Future<void> loadMessages() async {
    if (active.isNotEmpty) messages=await api('/chats/$active/messages');
    if(mounted) setState(() {});
  }
  Future<void> send() async {
    if(waiting||draft.text.trim().isEmpty)return;
    setState(()=>waiting=true);
    try {
      if(active.isEmpty)await loadChats();
      if(active.isEmpty)return;
      await api('/chats/$active/send',method:'POST',data:{'text':draft.text.trim()});
      draft.clear();
      await loadChats();
    } catch(e){status='$e';}
    finally{if(mounted)setState(()=>waiting=false);}
  }
  @override Widget build(BuildContext context) => Scaffold(
    appBar:AppBar(title:const Text('✿ Sayuri · общий чат')),
    drawer:token.isEmpty?null:Drawer(child:SafeArea(child:ListView(children:[
      const ListTile(title:Text('Sayuri')),
      const ListTile(subtitle:Text('Наставник отвечает · Sayuri учится')),
      ListTile(title:const Text('Выйти'),onTap:() async {
        await storage.delete(key:'token');token='';messages=[];setState(() {});
        if(context.mounted)Navigator.pop(context);
      })
    ]))),
    body:token.isEmpty
      ? Padding(padding:const EdgeInsets.all(20),child:ListView(children:[
          const Text('Подключение к серверу Sayuri'),
          TextField(controller:address,decoration:const InputDecoration(labelText:'https://адрес-сервера')),
          TextField(controller:password,obscureText:true,decoration:const InputDecoration(labelText:'Пароль владельца')),
          const SizedBox(height:12),
          FilledButton(onPressed:()=>login(),child:const Text('Войти')),
          TextButton(onPressed:()=>login(first:true),child:const Text('Первый запуск: создать владельца')),
          Text(status)
        ]))
      : Column(children:[
          if(status.isNotEmpty)Text(status,style:const TextStyle(color:Colors.orangeAccent)),
          Expanded(child:ListView.builder(reverse:true,itemCount:messages.length,itemBuilder:(context,i){
            final m=messages[messages.length-i-1],user=m['role']=='user';
            return Align(alignment:user?Alignment.centerRight:Alignment.centerLeft,
              child:Container(margin:const EdgeInsets.all(8),padding:const EdgeInsets.all(12),
                constraints:const BoxConstraints(maxWidth:330),
                decoration:BoxDecoration(color:user?const Color(0xff483c68):const Color(0xff273343),borderRadius:BorderRadius.circular(16)),
                child:Text(m['text'])));
          })),
          Padding(padding:const EdgeInsets.all(12),child:Row(children:[
            Expanded(child:TextField(controller:draft,minLines:1,maxLines:4,decoration:const InputDecoration(hintText:'Написать наставнику…'))),
            IconButton(onPressed:waiting?null:send,icon:waiting?const CircularProgressIndicator():const Icon(Icons.send))
          ]))
        ])
  );
}
